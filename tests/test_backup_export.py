"""Снимок SQLite и пакетная выгрузка лидов."""

import gzip
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

LEAD = {
    "name": "Клиент",
    "phone": "",
    "object_type": "Квартира",
    "budget": "lo",
    "status": "lead",
}
AUTH = ("crm", "test")


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    db_path = tmp_path / "crm.db"
    monkeypatch.setenv("CRM_FILES_DIR", str(tmp_path / "files"))
    import backend.database as database

    monkeypatch.setattr(database, "DB_PATH", db_path)
    return db_path


@pytest.fixture()
def client(storage, monkeypatch):
    monkeypatch.delenv("CRM_BASIC_USER", raising=False)
    monkeypatch.delenv("CRM_BASIC_PASSWORD", raising=False)
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


def _create(client: TestClient, name: str, **extra) -> int:
    body = dict(LEAD)
    body["name"] = name
    body.update(extra)
    response = client.post("/api/leads", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _freeze(db_path: Path, lead_id: int, stamp: str) -> None:
    """Ставит штампы вложенных строк, затем самого лида — триггер не затирает явное updated_at."""
    conn = sqlite3.connect(db_path)
    for table in ("notes", "messages", "payments", "lead_files"):
        conn.execute(f"UPDATE {table} SET created_at = ? WHERE lead_id = ?", (stamp, lead_id))
    conn.execute(
        "UPDATE leads SET created_at = ?, updated_at = ? WHERE id = ?",
        (stamp, stamp, lead_id),
    )
    conn.commit()
    conn.close()


def _open_backup(payload: bytes, dest: Path) -> sqlite3.Connection:
    dest.write_bytes(payload)
    return sqlite3.connect(dest)


def _merged_notes(client: TestClient, lead_id: int) -> list[dict]:
    objects = client.get(f"/api/leads/{lead_id}/objects").json()
    notes = list(client.get(f"/api/leads/{lead_id}/notes").json())
    for obj in objects:
        notes.extend(
            client.get(f"/api/leads/{lead_id}/notes", params={"lead_object_id": obj["id"]}).json()
        )
    notes.sort(key=lambda note: (note["created_at"] or "", note["id"]), reverse=True)
    return notes


def test_backup_is_valid_sqlite_and_leaves_nothing(client, storage, tmp_path):
    lead_id = _create(client, "Архив")
    client.post(
        f"/api/leads/{lead_id}/messages/bulk",
        json=[{"text": "Привет", "direction": "in", "source": "Телефон", "created_at": "2024-02-01 10:00:00"}],
    )
    client.post(f"/api/leads/{lead_id}/payments", json={"paid_at": "2024-02-02", "amount": 1000, "note": "аванс"})

    response = client.get("/api/admin/backup", auth=AUTH)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/octet-stream")
    assert 'filename="crm.db"' in response.headers["content-disposition"]
    assert response.content.startswith(b"SQLite format 3\x00")

    conn = _open_backup(response.content, tmp_path / "snap.db")
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT name FROM leads").fetchone()[0] == "Архив"
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"leads", "notes", "messages", "payments", "lead_objects"} <= tables
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1
    assert conn.execute("SELECT amount FROM payments").fetchone()[0] == 1000
    conn.close()

    assert client.get(f"/api/leads/{lead_id}").json()["name"] == "Архив"
    later = _create(client, "После снимка")
    assert client.get(f"/api/leads/{later}").status_code == 200
    assert list(Path(tempfile.gettempdir()).glob("crm-backup-*")) == []
    assert list(storage.parent.glob("crm-backup-*")) == []
    assert storage.is_file()

    packed = client.get("/api/admin/backup", params={"gzip": 1}, auth=AUTH)
    assert packed.status_code == 200, packed.text
    assert packed.headers["content-type"].startswith("application/gzip")
    assert 'filename="crm.db.gz"' in packed.headers["content-disposition"]
    raw = gzip.decompress(packed.content)
    gz_conn = _open_backup(raw, tmp_path / "snap-gz.db")
    names = {row[0] for row in gz_conn.execute("SELECT name FROM leads")}
    gz_conn.close()
    assert {"Архив", "После снимка"} <= names
    assert list(Path(tempfile.gettempdir()).glob("crm-backup-*")) == []


def test_export_matches_per_lead_endpoints(client, storage):
    assert client.get("/api/leads/export", auth=AUTH).json() == []

    multi = _create(client, "Несколько", has_multiple_objects=True, deal_amount=500000)
    single = _create(client, "Один")
    obj = client.post(
        f"/api/leads/{multi}/objects",
        json={"name": "Кухня", "address": "Ленина 1", "object_type": "Квартира", "budget": "mid", "deal_amount": 80000},
    ).json()
    client.post(f"/api/leads/{multi}/notes", json={"text": "Общая заметка"})
    client.post(f"/api/leads/{multi}/notes", json={"text": "Заметка объекта", "lead_object_id": obj["id"]})
    client.post(f"/api/leads/{single}/notes", json={"text": "Только лид"})
    client.post(
        f"/api/leads/{multi}/messages/bulk",
        json=[
            {"text": "Первое", "direction": "in", "source": "Авито", "created_at": "2024-03-01 09:00:00"},
            {"text": "Второе", "direction": "out", "source": "Авито", "created_at": "2024-03-02 09:00:00"},
        ],
    )
    client.post(
        f"/api/leads/{multi}/payments",
        json={"paid_at": "2024-03-10", "amount": 40000, "note": "1", "object_id": obj["id"]},
    )
    client.post(f"/api/leads/{multi}/payments", json={"paid_at": "2024-04-01", "amount": 15000, "note": "2"})
    uploaded = client.post(
        f"/api/leads/{multi}/files",
        files=[("files", ("plan.txt", b"UNIQUEFILEBODY", "text/plain"))],
    )
    assert uploaded.status_code == 200, uploaded.text

    conn = sqlite3.connect(storage)
    conn.execute("UPDATE notes SET created_at = ? WHERE text = ?", ("2024-03-02 12:00:00", "Общая заметка"))
    conn.execute("UPDATE notes SET created_at = ? WHERE text = ?", ("2024-03-03 12:00:00", "Заметка объекта"))
    conn.execute("UPDATE notes SET created_at = ? WHERE text = ?", ("2024-01-01 08:00:00", "Только лид"))
    conn.commit()
    conn.close()

    exported = client.get("/api/leads/export", auth=AUTH).json()
    assert [row["id"] for row in exported] == [multi, single]
    blob = client.get("/api/leads/export", auth=AUTH).text
    assert "UNIQUEFILEBODY" not in blob
    assert "stored_name" not in blob

    by_id = {row["id"]: row for row in exported}
    for lead_id in (multi, single):
        detail = client.get(f"/api/leads/{lead_id}").json()
        row = by_id[lead_id]
        for key, value in detail.items():
            if key in ("objects", "payments"):
                continue
            assert row[key] == value, key
        assert row["objects"] == client.get(f"/api/leads/{lead_id}/objects").json()
        assert row["messages"] == client.get(f"/api/leads/{lead_id}/messages").json()
        assert row["files"] == client.get(f"/api/leads/{lead_id}/files").json()
        assert row["payments"] == client.get(f"/api/leads/{lead_id}/payments").json()
        assert row["payments"] == detail["payments"]
        assert row["notes"] == _merged_notes(client, lead_id)
        assert "stored_name" not in {key for item in row["files"] for key in item}
        assert all(set(item) >= {"id", "lead_id", "original_name", "mime_type", "size", "url", "is_image"} for item in row["files"])

    assert len(by_id[multi]["notes"]) == 2
    assert by_id[multi]["notes"][0]["text"] == "Заметка объекта"
    assert len(by_id[multi]["files"]) == 1
    assert by_id[multi]["files"][0]["original_name"] == "plan.txt"
    assert by_id[single]["objects"] == []
    assert by_id[single]["messages"] == []
    assert by_id[single]["files"] == []
    assert by_id[single]["payments"] == []

    listed = client.get("/api/leads").json()
    assert "notes" not in listed[0]
    assert "messages" not in listed[0]
    assert "files" not in listed[0]
    assert "payments" in listed[0]
    assert "files_count" in listed[0]


def test_include_and_updated_since(client, storage):
    changed = _create(client, "Менялся")
    quiet = _create(client, "Тихий")
    nested = _create(client, "Вложение")
    touched = _create(client, "Объект")

    client.post(f"/api/leads/{changed}/notes", json={"text": "старая"})
    client.post(f"/api/leads/{quiet}/notes", json={"text": "тишина"})
    client.post(f"/api/leads/{nested}/notes", json={"text": "заметка"})
    client.post(
        f"/api/leads/{nested}/messages",
        json={"text": "свежее", "direction": "in", "source": "Телефон"},
    )
    client.put(
        f"/api/leads/{touched}",
        json={**LEAD, "name": "Объект", "has_multiple_objects": True},
    )
    obj = client.post(f"/api/leads/{touched}/objects", json={"name": "Дом"}).json()

    old = "2020-01-01 00:00:00"
    for lead_id in (changed, quiet, nested, touched):
        _freeze(storage, lead_id, old)

    conn = sqlite3.connect(storage)
    conn.execute(
        "UPDATE messages SET created_at = ? WHERE lead_id = ?",
        ("2024-05-01 08:00:00", nested),
    )
    conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", (old, nested))
    conn.commit()
    conn.close()

    renamed = client.put(f"/api/leads/{changed}", json={**LEAD, "name": "Менялся сегодня"})
    assert renamed.status_code == 200, renamed.text
    edited = client.put(
        f"/api/leads/{touched}/objects/{obj['id']}",
        json={"name": "Дом обновлён"},
    )
    assert edited.status_code == 200, edited.text

    since = "2024-01-01T00:00:00"
    rows = client.get("/api/leads/export", params={"updated_since": since}, auth=AUTH).json()
    found = {row["name"] for row in rows}
    assert "Менялся сегодня" in found
    assert "Вложение" in found
    assert "Объект" in found
    assert "Тихий" not in found

    notes_only = client.get(
        "/api/leads/export",
        params={"updated_since": since, "include": "notes"},
        auth=AUTH,
    ).json()
    nested_row = next(row for row in notes_only if row["id"] == nested)
    assert set(nested_row) >= {"id", "name", "notes"}
    assert "messages" not in nested_row
    assert "files" not in nested_row
    assert "payments" not in nested_row
    assert "objects" not in nested_row
    assert nested_row["notes"] == _merged_notes(client, nested)

    limited = client.get(
        "/api/leads/export",
        params={"include": "notes,payments"},
        auth=AUTH,
    ).json()
    assert len(limited) == 4
    sample = next(row for row in limited if row["id"] == changed)
    assert set(sample) >= {"notes", "payments"}
    assert "messages" not in sample and "files" not in sample and "objects" not in sample

    exact = client.get(
        "/api/leads/export",
        params={"updated_since": "2020-01-01T00:00:00"},
        auth=AUTH,
    ).json()
    assert {row["id"] for row in exact} >= {changed, quiet, nested, touched}
    later = client.get(
        "/api/leads/export",
        params={"updated_since": "2099-01-01T00:00:00"},
        auth=AUTH,
    ).json()
    assert later == []

    assert client.get("/api/leads/export", params={"updated_since": "32.13.25"}, auth=AUTH).status_code == 400
    assert client.get("/api/leads/export", params={"include": "notes,secret"}, auth=AUTH).status_code == 400
    assert client.get("/api/leads").status_code == 200


def test_auth_required_and_existing_routes_stay(client, monkeypatch):
    assert client.get("/api/admin/backup").status_code == 401
    assert client.get("/api/leads/export").status_code == 401
    assert client.get("/api/leads").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/leads/export", auth=AUTH).status_code == 200

    monkeypatch.setenv("CRM_BASIC_USER", "crm")
    monkeypatch.setenv("CRM_BASIC_PASSWORD", "secret")
    assert client.get("/api/admin/backup", auth=("crm", "nope")).status_code == 401
    assert client.get("/api/leads/export", auth=("other", "secret")).status_code == 401
    assert client.get("/api/leads/export", auth=("crm", "secret")).status_code == 200
    assert client.get("/api/admin/backup", auth=("crm", "secret")).status_code == 200
    assert client.get("/api/leads").status_code == 200

    from backend.main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/avito/webhook" in paths
    assert "/api/leads/{lead_id}/send-avito" in paths
    assert "/api/leads/{lead_id}/files" in paths
    assert "/api/leads/{lead_id}/files/{file_id}" in paths
    assert "/api/leads/{lead_id}/payments" in paths
