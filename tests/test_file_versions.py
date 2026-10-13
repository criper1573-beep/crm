"""История версий файлов лида. Старая загрузка остаётся отдельным путём."""

import gzip
import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.files import FILE_CATEGORIES

LEAD = {
    "name": "Клиент",
    "phone": "",
    "object_type": "Квартира",
    "budget": "lo",
    "status": "lead",
}
AUTH = ("crm", "test")
FILE_KEYS = {"id", "lead_id", "original_name", "mime_type", "size", "created_at", "url", "is_image"}
VERSION_COLUMNS = [
    "id",
    "lead_id",
    "filename",
    "version",
    "category",
    "author",
    "comment",
    "original_name",
    "sha256",
    "size",
    "stored_name",
    "created_at",
]


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    db_path = tmp_path / "crm.db"
    files_dir = tmp_path / "files"
    monkeypatch.setenv("CRM_FILES_DIR", str(files_dir))
    import backend.database as database
    import backend.files as files

    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(files, "FILES_DIR", files_dir)
    return db_path, files_dir


@pytest.fixture()
def client(storage, monkeypatch):
    monkeypatch.delenv("CRM_BASIC_USER", raising=False)
    monkeypatch.delenv("CRM_BASIC_PASSWORD", raising=False)
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


def _create(client: TestClient, name: str = "Клиент") -> int:
    body = dict(LEAD)
    body["name"] = name
    response = client.post("/api/leads", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _post_version(
    client: TestClient,
    lead_id: int,
    content: bytes,
    *,
    upload_name: str = "plan.txt",
    filename: str | None = None,
    category: str = "смета",
    author: str = "бот",
    comment: str = "",
    auth=AUTH,
):
    data = {"category": category, "author": author, "comment": comment}
    if filename is not None:
        data["filename"] = filename
    return client.post(
        f"/api/leads/{lead_id}/files/versions",
        data=data,
        files={"file": (upload_name, content, "application/octet-stream")},
        auth=auth,
    )


def _history(client: TestClient, lead_id: int, **params) -> list[dict]:
    response = client.get(f"/api/leads/{lead_id}/files/versions", params=params, auth=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def _files_count(client: TestClient, lead_id: int) -> int:
    rows = client.get("/api/leads").json()
    return next(row["files_count"] for row in rows if row["id"] == lead_id)


def _disk(files_dir: Path, lead_id: int) -> list[Path]:
    folder = files_dir / str(lead_id)
    if not folder.exists():
        return []
    return sorted(path for path in folder.iterdir() if path.is_file())


def _notes_count(db_path: Path, lead_id: int) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM notes WHERE lead_id = ?", (lead_id,)).fetchone()[0]
    finally:
        conn.close()


def test_v1_v2_skip_same_hash_and_keep_card(client, storage):
    db_path, files_dir = storage
    lead_id = _create(client)
    from backend.files import init_table

    init_table()
    init_table()

    first = _post_version(client, lead_id, b"version-one", comment="первая", author="  бот  ")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["skipped"] is False
    assert body["version"] == 1
    assert body["filename"] == "plan.txt"
    assert body["category"] == "смета"
    assert body["author"] == "бот"
    assert body["comment"] == "первая"
    assert body["sha256"] == hashlib.sha256(b"version-one").hexdigest()
    assert body["size"] == len(b"version-one")
    assert "stored_name" not in body
    v1_id = body["id"]

    same = _post_version(client, lead_id, b"version-one", comment="другой", category="кп", author="другой")
    assert same.status_code == 200, same.text
    assert same.json() == {"skipped": True, "version": 1}
    assert len(_disk(files_dir, lead_id)) == 1
    assert _history(client, lead_id)[0]["comment"] == "первая"
    assert _history(client, lead_id)[0]["category"] == "смета"

    other_name = _post_version(
        client, lead_id, b"version-one", upload_name="other.txt", filename="other.txt", category="план"
    )
    assert other_name.status_code == 200, other_name.text
    assert other_name.json()["skipped"] is False
    assert other_name.json()["version"] == 1
    assert other_name.json()["filename"] == "other.txt"

    second = _post_version(client, lead_id, b"version-two", comment="вторая")
    assert second.status_code == 200, second.text
    assert second.json()["skipped"] is False
    assert second.json()["version"] == 2
    assert second.json()["sha256"] == hashlib.sha256(b"version-two").hexdigest()
    v2_id = second.json()["id"]

    again = _post_version(client, lead_id, b"version-two")
    assert again.json() == {"skipped": True, "version": 2}

    third = _post_version(client, lead_id, b"version-one", comment="снова первая")
    assert third.status_code == 200, third.text
    assert third.json()["skipped"] is False
    assert third.json()["version"] == 3

    history = _history(client, lead_id, filename="plan.txt")
    assert [item["version"] for item in history] == [3, 2, 1]
    assert "stored_name" not in history[0]
    assert [item["id"] for item in history] == [third.json()["id"], v2_id, v1_id]
    assert _history(client, lead_id, filename="missing.txt") == []

    listed = client.get(f"/api/leads/{lead_id}/files").json()
    plan = next(item for item in listed if item["original_name"] == "plan.txt")
    assert set(plan) == FILE_KEYS
    assert plan["size"] == len(b"version-one")
    preview = client.get(plan["url"])
    assert preview.status_code == 200
    assert preview.content == b"version-one"
    assert _files_count(client, lead_id) == 2

    conn = sqlite3.connect(db_path)
    card = conn.execute(
        "SELECT stored_name, version, sha256, category FROM lead_files WHERE lead_id = ? AND original_name = ?",
        (lead_id, "plan.txt"),
    ).fetchone()
    latest = conn.execute(
        """
        SELECT stored_name, sha256 FROM lead_file_versions
        WHERE lead_id = ? AND filename = ? ORDER BY version DESC LIMIT 1
        """,
        (lead_id, "plan.txt"),
    ).fetchone()
    cols = [row[1] for row in conn.execute("PRAGMA table_info(lead_file_versions)")]
    triggers = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    conn.close()
    assert card[0] == latest[0]
    assert card[1] == 3
    assert card[2] == latest[1]
    assert card[3] == "смета"
    assert cols == VERSION_COLUMNS
    for name in (
        "trg_lead_files_ins_touch",
        "trg_lead_files_upd_touch",
        "trg_lead_files_del_touch",
        "trg_notes_ins_touch",
        "trg_messages_ins_touch",
        "trg_payments_ins_touch",
    ):
        assert name in triggers
    assert _notes_count(db_path, lead_id) == 0
    assert all(path.parent.resolve() == (files_dir / str(lead_id)).resolve() for path in _disk(files_dir, lead_id))
    assert not any(path.name.endswith(".part") for path in _disk(files_dir, lead_id))

    raw = client.get(f"/api/leads/{lead_id}/files/versions/{v1_id}/raw", auth=AUTH)
    assert raw.status_code == 200
    assert raw.content == b"version-one"
    assert "attachment" in raw.headers["content-disposition"].lower()
    assert client.get(f"/api/leads/{lead_id}/files/versions/{v2_id}/raw", auth=AUTH).content == b"version-two"


def test_history_is_newest_first_and_filters(client, storage):
    db_path, _files_dir = storage
    lead_id = _create(client, "История")
    other = _create(client, "Чужой")
    early = _post_version(client, lead_id, b"early", upload_name="a.txt", filename="a.txt", category="договор")
    late = _post_version(client, lead_id, b"late", upload_name="a.txt", filename="a.txt", category="фото")
    mid = _post_version(client, lead_id, b"mid", upload_name="b.txt", filename="b.txt", category="ведомость")
    assert early.status_code == late.status_code == mid.status_code == 200

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE lead_file_versions SET created_at = ? WHERE id = ?",
        ("2024-06-01 10:00:00", early.json()["id"]),
    )
    conn.execute(
        "UPDATE lead_file_versions SET created_at = ? WHERE id = ?",
        ("2024-01-01 10:00:00", late.json()["id"]),
    )
    conn.execute(
        "UPDATE lead_file_versions SET created_at = ? WHERE id = ?",
        ("2024-03-01 10:00:00", mid.json()["id"]),
    )
    conn.commit()
    conn.close()

    history = _history(client, lead_id)
    assert [(item["filename"], item["version"]) for item in history] == [
        ("a.txt", 1),
        ("b.txt", 1),
        ("a.txt", 2),
    ]
    assert [(item["filename"], item["version"]) for item in _history(client, lead_id, since="2024-03-01")] == [
        ("a.txt", 1),
        ("b.txt", 1),
    ]
    assert [item["version"] for item in _history(client, lead_id, filename="a.txt")] == [1, 2]
    assert _history(client, lead_id, since="2024-03-01", filename="a.txt")[0]["id"] == early.json()["id"]
    assert _history(client, lead_id, since="2099-01-01") == []
    assert client.get(
        f"/api/leads/{lead_id}/files/versions", params={"since": "32-13-01"}, auth=AUTH
    ).status_code == 400
    assert _history(client, other) == []
    assert client.get(f"/api/leads/{other}/files/versions/{early.json()['id']}/raw", auth=AUTH).status_code == 404


def test_download_old_version_and_delete(client, storage):
    db_path, files_dir = storage
    lead_id = _create(client, "Удаление")
    other = _create(client, "Сосед")
    first = _post_version(client, lead_id, b"AAA", comment="v1", category="чертёж")
    second = _post_version(client, lead_id, b"BBB", comment="v2", category="материалы")
    assert first.status_code == second.status_code == 200
    v1 = first.json()["id"]
    v2 = second.json()["id"]
    assert client.get(f"/api/leads/{lead_id}/files/versions/{v1}/raw", auth=AUTH).content == b"AAA"
    assert client.get(f"/api/leads/{lead_id}/files").json()[0]["size"] == 3
    assert client.get(client.get(f"/api/leads/{lead_id}/files").json()[0]["url"]).content == b"BBB"

    assert client.delete(f"/api/leads/{other}/files/versions/{v1}", auth=AUTH).status_code == 404
    assert client.get(f"/api/leads/{lead_id}/files/versions/{v1}/raw", auth=AUTH).content == b"AAA"

    removed_old = client.delete(f"/api/leads/{lead_id}/files/versions/{v1}", auth=AUTH)
    assert removed_old.status_code == 200
    assert removed_old.json() == {"ok": True}
    assert client.get(f"/api/leads/{lead_id}/files/versions/{v1}/raw", auth=AUTH).status_code == 404
    assert [item["version"] for item in _history(client, lead_id)] == [2]
    assert client.get(client.get(f"/api/leads/{lead_id}/files").json()[0]["url"]).content == b"BBB"
    assert len(_disk(files_dir, lead_id)) == 1
    assert _notes_count(db_path, lead_id) == 0

    removed_latest = client.delete(f"/api/leads/{lead_id}/files/versions/{v2}", auth=AUTH)
    assert removed_latest.status_code == 200
    assert _history(client, lead_id) == []
    assert client.get(f"/api/leads/{lead_id}/files").json() == []
    assert _files_count(client, lead_id) == 0
    assert _disk(files_dir, lead_id) == []
    assert client.delete(f"/api/leads/{lead_id}/files/versions/{v2}", auth=AUTH).status_code == 404

    rolled_v1 = _post_version(client, lead_id, b"AAA", category="план")
    rolled_v2 = _post_version(client, lead_id, b"BBB", category="план")
    assert rolled_v1.json()["version"] == 1
    assert rolled_v2.json()["version"] == 2
    gone = client.delete(
        f"/api/leads/{lead_id}/files/versions/{rolled_v2.json()['id']}", auth=AUTH
    )
    assert gone.status_code == 200
    assert [item["version"] for item in _history(client, lead_id)] == [1]
    card = client.get(f"/api/leads/{lead_id}/files").json()
    assert len(card) == 1
    assert client.get(card[0]["url"]).content == b"AAA"
    assert client.get(
        f"/api/leads/{lead_id}/files/versions/{rolled_v1.json()['id']}/raw", auth=AUTH
    ).content == b"AAA"
    assert _files_count(client, lead_id) == 1
    assert len(_disk(files_dir, lead_id)) == 1

    card_id = card[0]["id"]
    assert client.delete(f"/api/leads/{lead_id}/files/{card_id}").status_code == 200
    assert client.get(f"/api/leads/{lead_id}/files").json() == []
    assert _files_count(client, lead_id) == 0
    assert client.get(
        f"/api/leads/{lead_id}/files/versions/{rolled_v1.json()['id']}/raw", auth=AUTH
    ).content == b"AAA"
    assert len(_disk(files_dir, lead_id)) == 1
    assert _notes_count(db_path, lead_id) == 0


def test_unknown_category_is_400_and_whitelist_passes(client, storage):
    _db_path, files_dir = storage
    lead_id = _create(client, "Категории")
    for index, category in enumerate(FILE_CATEGORIES):
        response = _post_version(
            client,
            lead_id,
            f"cat-{index}".encode(),
            upload_name=f"f{index}.bin",
            filename=f"f{index}.bin",
            category=category,
        )
        assert response.status_code == 200, response.text
        assert response.json()["category"] == category
        assert response.json()["skipped"] is False

    folded = _post_version(
        client, lead_id, b"case", upload_name="case.bin", filename="case.bin", category="  Смета  "
    )
    assert folded.status_code == 200, folded.text
    assert folded.json()["category"] == "смета"

    before = len(_history(client, lead_id))
    before_disk = len(_disk(files_dir, lead_id))
    for bad in ("", "чертеж", "секретно", "смета extra"):
        response = _post_version(
            client, lead_id, b"nope", upload_name="bad.bin", filename="bad.bin", category=bad
        )
        assert response.status_code == 400, bad
        assert response.json()["detail"] == "Unknown category"
    assert len(_history(client, lead_id)) == before
    assert len(_disk(files_dir, lead_id)) == before_disk
    assert client.get(f"/api/leads/{lead_id}/notes").json() == []


def test_legacy_upload_list_preview_delete_and_backup(client, storage, tmp_path):
    db_path, files_dir = storage
    lead_id = _create(client, "Старый")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", ("1999-01-01 00:00:00", lead_id))
    conn.commit()
    conn.close()

    uploaded = client.post(
        f"/api/leads/{lead_id}/files",
        files=[("files", ("photo.png", b"png-bytes", "image/png"))],
    )
    assert uploaded.status_code == 200, uploaded.text
    item = uploaded.json()[0]
    assert set(item) == FILE_KEYS
    assert item["original_name"] == "photo.png"
    assert item["is_image"] is True
    assert item["mime_type"] == "image/png"
    listed = client.get(f"/api/leads/{lead_id}/files")
    assert listed.status_code == 200
    assert listed.json() == uploaded.json()
    preview = client.get(item["url"])
    assert preview.status_code == 200
    assert preview.content == b"png-bytes"
    assert preview.headers["content-type"].startswith("image/png")
    assert "inline" in preview.headers["content-disposition"].lower()
    assert _files_count(client, lead_id) == 1
    ui_history = _history(client, lead_id)
    assert len(ui_history) == 1
    assert ui_history[0]["author"] == "ui"
    assert ui_history[0]["filename"] == "photo.png"
    assert ui_history[0]["version"] == 1
    assert ui_history[0]["original_name"] == "photo.png"
    assert ui_history[0]["sha256"] == hashlib.sha256(b"png-bytes").hexdigest()

    conn = sqlite3.connect(db_path)
    legacy = conn.execute(
        "SELECT category, version, sha256 FROM lead_files WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    version_rows = conn.execute("SELECT COUNT(*) FROM lead_file_versions").fetchone()[0]
    updated = conn.execute("SELECT updated_at FROM leads WHERE id = ?", (lead_id,)).fetchone()[0]
    conn.close()
    assert legacy == ("прочее", 1, hashlib.sha256(b"png-bytes").hexdigest())
    assert version_rows == 1
    assert updated != "1999-01-01 00:00:00"
    assert _notes_count(db_path, lead_id) == 0

    exported = client.get("/api/leads/export", auth=AUTH)
    assert exported.status_code == 200
    row = next(item for item in exported.json() if item["id"] == lead_id)
    assert row["files"] == listed.json()
    assert "stored_name" not in exported.text
    assert "png-bytes" not in exported.text

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", ("1999-01-01 00:00:00", lead_id))
    conn.commit()
    conn.close()
    skipped_setup = _post_version(client, lead_id, b"png-bytes", upload_name="photo.png", filename="photo.png")
    assert skipped_setup.status_code == 200
    # UI уже записал эти байты как версию 1, повтор с тем же sha256 — пропуск.
    assert skipped_setup.json() == {"skipped": True, "version": 1}
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", ("1999-02-02 00:00:00", lead_id))
    conn.commit()
    conn.close()
    skipped = _post_version(client, lead_id, b"png-bytes", upload_name="photo.png", filename="photo.png")
    assert skipped.json() == {"skipped": True, "version": 1}
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT updated_at FROM leads WHERE id = ?", (lead_id,)).fetchone()[0] == "1999-02-02 00:00:00"
    conn.close()

    fresh = _post_version(client, lead_id, b"png-bytes-v2", upload_name="photo.png", filename="photo.png")
    assert fresh.json()["version"] == 2
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT updated_at FROM leads WHERE id = ?", (lead_id,)).fetchone()[0] != "1999-02-02 00:00:00"
    conn.close()

    backup = client.get("/api/admin/backup", auth=AUTH)
    assert backup.status_code == 200
    snap = tmp_path / "snap.db"
    snap.write_bytes(backup.content)
    saved = sqlite3.connect(snap)
    assert saved.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert saved.execute("SELECT COUNT(*) FROM lead_file_versions WHERE lead_id = ?", (lead_id,)).fetchone()[0] == 2
    assert saved.execute(
        "SELECT version FROM lead_files WHERE lead_id = ? AND original_name = ?",
        (lead_id, "photo.png"),
    ).fetchone()[0] == 2
    saved.close()
    assert all((files_dir.resolve() in path.resolve().parents) for path in _disk(files_dir, lead_id))

    packed = client.get("/api/admin/backup", params={"gzip": 1}, auth=AUTH)
    assert packed.status_code == 200
    gz_path = tmp_path / "gz.db"
    gz_path.write_bytes(gzip.decompress(packed.content))
    gz_conn = sqlite3.connect(gz_path)
    assert gz_conn.execute("SELECT COUNT(*) FROM lead_file_versions").fetchone()[0] == 2
    gz_conn.close()

    file_id = client.get(f"/api/leads/{lead_id}/files").json()[0]["id"]
    # В карточке одна строка на имя, на диске две версии.
    assert _files_count(client, lead_id) == 1
    assert len(_disk(files_dir, lead_id)) == 2
    assert client.delete(f"/api/leads/{lead_id}/files/{file_id}").json() == {"ok": True}
    assert client.get(f"/api/leads/{lead_id}/files/{file_id}").status_code == 404
    assert client.get(f"/api/leads/{lead_id}/files").json() == []
    assert _files_count(client, lead_id) == 0
    # Удаление карточки не стирает историю и байты версий.
    assert len(_history(client, lead_id, filename="photo.png")) == 2
    assert len(_disk(files_dir, lead_id)) == 2

    solo = client.post(
        f"/api/leads/{lead_id}/files",
        files=[("files", ("note.txt", b"solo", "text/plain"))],
    )
    assert solo.status_code == 200, solo.text
    solo_id = solo.json()[0]["id"]
    assert client.delete(f"/api/leads/{lead_id}/files/{solo_id}").status_code == 200
    assert client.get(f"/api/leads/{lead_id}/files/{solo_id}").status_code == 404
    # Карточка снята, версия UI и байты note.txt остаются вместе с двумя версиями фото.
    assert len(_disk(files_dir, lead_id)) == 3
    note_versions = _history(client, lead_id, filename="note.txt")
    assert len(note_versions) == 1
    assert note_versions[0]["author"] == "ui"
    assert client.get(
        f"/api/leads/{lead_id}/files/versions/{note_versions[0]['id']}/raw", auth=AUTH
    ).content == b"solo"
    conn = sqlite3.connect(db_path)
    left = conn.execute(
        "SELECT COUNT(*) FROM lead_files WHERE lead_id = ? AND original_name = ?",
        (lead_id, "note.txt"),
    ).fetchone()[0]
    conn.close()
    assert left == 0
    assert _notes_count(db_path, lead_id) == 0


def test_existing_table_gains_columns_without_rewriting_rows(tmp_path, monkeypatch):
    """Прод: lead_files уже есть. Миграция только добавляет колонки и новую таблицу."""
    db_path = tmp_path / "crm.db"
    monkeypatch.setenv("CRM_FILES_DIR", str(tmp_path / "files"))
    import backend.database as database
    import backend.files as files

    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(files, "FILES_DIR", tmp_path / "files")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, name TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO leads (id, name, updated_at) VALUES (1, 'old', '2020-01-01 00:00:00')")
    conn.execute(
        """
        CREATE TABLE lead_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            size INTEGER NOT NULL DEFAULT 0,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO lead_files (lead_id, original_name, stored_name, mime_type, size, created_at)
        VALUES (1, 'old.txt', ?, 'text/plain', 3, '2020-01-01 00:00:00')
        """,
        ("a" * 32,),
    )
    conn.commit()
    conn.close()

    files.init_table()
    files.init_table()

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(lead_files)")]
    row = conn.execute(
        "SELECT original_name, category, version, sha256, created_at FROM lead_files"
    ).fetchone()
    updated = conn.execute("SELECT updated_at FROM leads WHERE id = 1").fetchone()[0]
    version_cols = [row[1] for row in conn.execute("PRAGMA table_info(lead_file_versions)")]
    conn.close()
    assert {"category", "version", "sha256"} <= set(cols)
    assert row == ("old.txt", None, None, None, "2020-01-01 00:00:00")
    assert updated == "2020-01-01 00:00:00"
    assert version_cols == VERSION_COLUMNS


def test_existing_version_table_gains_original_name(tmp_path, monkeypatch):
    """Прод уже имеет lead_file_versions без original_name. Колонка добавляется, строка та же."""
    db_path = tmp_path / "crm.db"
    monkeypatch.setenv("CRM_FILES_DIR", str(tmp_path / "files"))
    import backend.database as database
    import backend.files as files

    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(files, "FILES_DIR", tmp_path / "files")
    digest = "b" * 64
    stored = "c" * 32
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE lead_file_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            version INTEGER NOT NULL,
            category TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT '',
            comment TEXT NOT NULL DEFAULT '',
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL DEFAULT 0,
            stored_name TEXT NOT NULL,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO lead_file_versions
            (lead_id, filename, version, category, author, comment, sha256, size, stored_name, created_at)
        VALUES (1, 'old_v2.xlsx', 2, 'смета', 'бот', 'заметка', ?, 4, ?, '2020-05-01 00:00:00')
        """,
        (digest, stored),
    )
    conn.commit()
    conn.close()

    files.init_table()
    files.init_table()

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(lead_file_versions)")]
    row = conn.execute(
        """
        SELECT filename, version, category, author, comment, original_name, sha256, stored_name, created_at
        FROM lead_file_versions
        """
    ).fetchone()
    conn.close()
    without = [name for name in VERSION_COLUMNS if name != "original_name"]
    assert cols == without + ["original_name"]
    assert row == (
        "old_v2.xlsx",
        2,
        "смета",
        "бот",
        "заметка",
        "",
        digest,
        stored,
        "2020-05-01 00:00:00",
    )


def test_version_auth_filename_and_missing_lead(client, monkeypatch, storage):
    _db_path, files_dir = storage
    lead_id = _create(client)
    assert client.post(
        f"/api/leads/{lead_id}/files/versions",
        data={"category": "прочее"},
        files={"file": ("a.txt", b"a", "text/plain")},
    ).status_code == 401
    assert client.get(f"/api/leads/{lead_id}/files/versions").status_code == 401
    assert client.get(f"/api/leads/{lead_id}/files/versions/1/raw").status_code == 401
    assert client.delete(f"/api/leads/{lead_id}/files/versions/1").status_code == 401

    monkeypatch.setenv("CRM_BASIC_USER", "crm")
    monkeypatch.setenv("CRM_BASIC_PASSWORD", "secret")
    assert _post_version(client, lead_id, b"a", auth=("crm", "nope")).status_code == 401
    assert client.get(f"/api/leads/{lead_id}/files/versions", auth=("other", "secret")).status_code == 401
    legacy = client.post(
        f"/api/leads/{lead_id}/files",
        files=[("files", ("legacy.txt", b"legacy", "text/plain"))],
    )
    assert legacy.status_code == 200, legacy.text

    named = _post_version(
        client,
        lead_id,
        b"bytes",
        upload_name="../../Смета.PDF",
        filename="",
        category="прочее",
        auth=("crm", "secret"),
    )
    assert named.status_code == 200, named.text
    assert named.json()["filename"] == "Смета.PDF"
    explicit = _post_version(
        client,
        lead_id,
        b"other-bytes",
        upload_name="ignored.bin",
        filename="ведомость.xlsx",
        category="ведомость",
        auth=("crm", "secret"),
    )
    assert explicit.json()["filename"] == "ведомость.xlsx"
    raw = client.get(
        f"/api/leads/{lead_id}/files/versions/{explicit.json()['id']}/raw",
        auth=("crm", "secret"),
    )
    assert raw.status_code == 200
    assert raw.content == b"other-bytes"
    assert "UTF-8" in raw.headers["content-disposition"]
    assert client.get("/api/leads/999999/files/versions", auth=("crm", "secret")).status_code == 404
    missing = _post_version(client, 999999, b"x", auth=("crm", "secret"))
    assert missing.status_code == 404
    assert _disk(files_dir, 999999) == []

    import backend.files as files

    monkeypatch.setattr(files, "MAX_FILE_SIZE", 4)
    too_big = _post_version(client, lead_id, b"12345", upload_name="big.bin", filename="big.bin", auth=("crm", "secret"))
    assert too_big.status_code == 413
    assert client.get(
        f"/api/leads/{lead_id}/files/versions",
        params={"filename": "big.bin"},
        auth=("crm", "secret"),
    ).json() == []
    assert not any(path.name.endswith(".part") for path in _disk(files_dir, lead_id))
