"""Документы лида: загрузка, скачивание, лимит, path traversal, авторизация, миграция."""

import os
import re
import sqlite3
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

os.environ["CRM_AUTH_ADMIN_PASSWORD"] = "admin-secret"
os.environ["CRM_AUTH_SONYA_PASSWORD"] = "sonya-secret"

ADMIN = ("admin", "admin-secret")
SONYA = ("sonya", "sonya-secret")

LEAD = {
    "name": "Тест",
    "phone": "+79990000000",
    "object_type": "Квартира",
    "budget": "lo",
    "status": "lead",
}


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    files = tmp_path / "files"
    db_path = tmp_path / "crm.db"
    monkeypatch.setenv("CRM_FILES_DIR", str(files))
    monkeypatch.setenv("CRM_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))
    monkeypatch.setenv("CRM_AUTH_ADMIN_PASSWORD", "admin-secret")
    monkeypatch.setenv("CRM_AUTH_SONYA_PASSWORD", "sonya-secret")
    import backend.database as database

    monkeypatch.setattr(database, "DB_PATH", db_path)
    return {"files": files, "db": db_path}


@pytest.fixture()
def client(storage):
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


def _create_lead(client: TestClient) -> dict:
    response = client.post("/api/leads", json=LEAD)
    assert response.status_code == 200, response.text
    return response.json()


def _upload(client: TestClient, lead_id: int, name: str, content: bytes, content_type: str, **data):
    return client.post(
        f"/api/leads/{lead_id}/files",
        files={"file": (name, content, content_type)},
        data=data,
        auth=ADMIN,
    )


def test_existing_lead_endpoints_work_without_file_auth(client):
    created = _create_lead(client)
    lead_id = created["id"]
    assert client.get("/api/leads").status_code == 200
    assert client.get(f"/api/leads/{lead_id}").status_code == 200
    note = client.post(f"/api/leads/{lead_id}/notes", json={"text": "заметка"})
    assert note.status_code == 200
    updated = dict(created)
    updated["comment"] = "как раньше"
    put = client.put(f"/api/leads/{lead_id}", json=updated)
    assert put.status_code == 200
    assert put.json()["comment"] == "как раньше"
    webhook = client.post("/api/avito/webhook", json={})
    assert webhook.status_code == 200
    send_missing = client.post("/api/leads/99999/send-avito", json={"text": "привет"})
    assert send_missing.status_code == 404
    assert client.delete(f"/api/leads/{lead_id}").status_code == 200


def test_file_endpoints_require_basic_auth(client):
    lead_id = _create_lead(client)["id"]
    uploaded = _upload(client, lead_id, "a.txt", b"hello", "text/plain")
    assert uploaded.status_code == 200
    file_id = uploaded.json()["id"]
    paths = [
        ("get", f"/api/leads/{lead_id}/files", None),
        ("post", f"/api/leads/{lead_id}/files", {"files": {"file": ("b.txt", b"x", "text/plain")}}),
        ("get", f"/api/leads/{lead_id}/files/{file_id}", None),
        ("delete", f"/api/leads/{lead_id}/files/{file_id}", None),
    ]
    for method, url, kwargs in paths:
        response = getattr(client, method)(url, **(kwargs or {}))
        assert response.status_code == 401, (method, url, response.status_code, response.text)
        assert "basic" in response.headers.get("www-authenticate", "").lower()
    wrong = client.get(f"/api/leads/{lead_id}/files", auth=("admin", "nope"))
    assert wrong.status_code == 401
    stranger = client.get(f"/api/leads/{lead_id}/files", auth=("bob", "admin-secret"))
    assert stranger.status_code == 401
    missing = client.post(
        "/api/leads/999999/files",
        files={"file": ("a.txt", b"x", "text/plain")},
    )
    assert missing.status_code == 401


def test_upload_missing_lead_is_404(client):
    response = client.post(
        "/api/leads/999999/files",
        files={"file": ("a.txt", b"abc", "text/plain")},
        auth=ADMIN,
    )
    assert response.status_code == 404


def test_upload_list_download_and_cyrillic_name(client):
    lead_id = _create_lead(client)["id"]
    payload = "Смета кухня".encode("utf-8") + b"\x00\xff\xfe"
    name = "Смета кухня.pdf"
    uploaded = _upload(
        client,
        lead_id,
        name,
        payload,
        "application/pdf",
        category="Смета",
        caption="Кухня 12 м",
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["original_name"] == name
    assert body["size"] == len(payload)
    assert body["content_type"] == "application/pdf"
    assert body["category"] == "Смета"
    assert body["caption"] == "Кухня 12 м"
    assert body["uploaded_by"] == "admin"
    assert body["created_at"]

    as_sonya = client.post(
        f"/api/leads/{lead_id}/files",
        files={"file": ("фото.png", b"\x89PNG", "image/png")},
        auth=SONYA,
    )
    assert as_sonya.status_code == 200
    assert as_sonya.json()["uploaded_by"] == "sonya"

    listed = client.get(f"/api/leads/{lead_id}/files", auth=SONYA)
    assert listed.status_code == 200
    rows = listed.json()
    assert {row["id"] for row in rows} == {body["id"], as_sonya.json()["id"]}
    assert all("stored_name" not in row for row in rows)
    pdf_row = next(row for row in rows if row["id"] == body["id"])
    assert pdf_row["original_name"] == name

    downloaded = client.get(f"/api/leads/{lead_id}/files/{body['id']}", auth=ADMIN)
    assert downloaded.status_code == 200
    assert downloaded.content == payload
    disposition = downloaded.headers["content-disposition"]
    match = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", disposition, re.I)
    assert match, disposition
    assert unquote(match.group(1)) == name
    assert "inline" in disposition.lower()

    forced = client.get(f"/api/leads/{lead_id}/files/{body['id']}?download=1", auth=ADMIN)
    assert forced.content == payload
    assert "attachment" in forced.headers["content-disposition"].lower()


def test_path_traversal_stays_inside_storage(client, storage):
    lead_id = _create_lead(client)["id"]
    outside = storage["files"].parent / "outside.txt"
    outside.write_bytes(b"sentinel")
    malicious = "../../outside.txt"
    uploaded = _upload(client, lead_id, malicious, b"pwned-not-sentinel", "text/plain")
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["original_name"] == malicious

    root = storage["files"].resolve()
    stored = [path for path in root.iterdir() if path.is_file()]
    assert len(stored) == 1
    assert stored[0].parent == root
    assert ".." not in stored[0].name
    assert stored[0].read_bytes() == b"pwned-not-sentinel"
    assert outside.read_bytes() == b"sentinel"
    assert not (root.parent / "etc" / "passwd").exists()

    from backend.lead_files import InvalidStoredName, resolve_stored_path

    with pytest.raises(InvalidStoredName):
        resolve_stored_path("../../etc/passwd")
    with pytest.raises(InvalidStoredName):
        resolve_stored_path(malicious)

    file_id = uploaded.json()["id"]
    conn = sqlite3.connect(storage["db"])
    conn.execute(
        "UPDATE lead_files SET stored_name = ? WHERE id = ?",
        ("../../etc/passwd", file_id),
    )
    conn.commit()
    conn.close()
    stolen = client.get(f"/api/leads/{lead_id}/files/{file_id}", auth=ADMIN)
    assert stolen.status_code == 404
    assert outside.read_bytes() == b"sentinel"


def test_file_over_limit_is_rejected(client, storage, monkeypatch):
    monkeypatch.setenv("CRM_MAX_UPLOAD_BYTES", "16")
    lead_id = _create_lead(client)["id"]
    response = _upload(client, lead_id, "big.bin", b"x" * 17, "application/octet-stream")
    assert response.status_code == 413
    root = storage["files"]
    root.mkdir(parents=True, exist_ok=True)
    assert list(root.iterdir()) == []
    listed = client.get(f"/api/leads/{lead_id}/files", auth=ADMIN)
    assert listed.status_code == 200
    assert listed.json() == []


def test_delete_file_and_delete_lead_remove_bytes(client, storage):
    lead_id = _create_lead(client)["id"]
    first = _upload(client, lead_id, "one.txt", b"one", "text/plain")
    second = _upload(client, lead_id, "two.txt", b"two", "text/plain")
    assert first.status_code == 200 and second.status_code == 200
    root = storage["files"].resolve()
    assert len(list(root.iterdir())) == 2

    removed = client.delete(
        f"/api/leads/{lead_id}/files/{first.json()['id']}",
        auth=ADMIN,
    )
    assert removed.status_code == 200
    assert removed.json() == {"ok": True}
    left = client.get(f"/api/leads/{lead_id}/files", auth=ADMIN).json()
    assert [row["id"] for row in left] == [second.json()["id"]]
    assert len(list(root.iterdir())) == 1

    other = client.get(f"/api/leads/{lead_id}/files/{second.json()['id'] + 100}", auth=ADMIN)
    assert other.status_code == 404

    assert client.delete(f"/api/leads/{lead_id}", auth=ADMIN).status_code == 200
    assert list(root.iterdir()) == []
    gone = client.get(f"/api/leads/{lead_id}/files", auth=ADMIN)
    assert gone.status_code == 404


def test_openapi_lists_document_endpoints(client):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    collection = "/api/leads/{lead_id}/files"
    item = "/api/leads/{lead_id}/files/{file_id}"
    assert "get" in paths[collection] and "post" in paths[collection]
    assert "get" in paths[item] and "delete" in paths[item]
    assert paths[collection]["post"].get("security")
    assert paths[collection]["get"].get("security")
    schemes = spec["components"]["securitySchemes"]
    assert any(
        scheme.get("type") == "http" and scheme.get("scheme") == "basic"
        for scheme in schemes.values()
    )
    assert not paths["/api/leads"]["get"].get("security")
    assert not paths["/api/avito/webhook"]["post"].get("security")


def test_migration_keeps_existing_rows(tmp_path, monkeypatch):
    import backend.database as database

    db_path = tmp_path / "crm.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")
    conn.execute("INSERT INTO leads (name) VALUES ('Сохранить')")
    conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, lead_id INTEGER, text TEXT)")
    conn.execute("INSERT INTO notes (lead_id, text) VALUES (1, 'заметка жива')")
    conn.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, lead_id INTEGER, text TEXT, direction TEXT, source TEXT)"
    )
    conn.execute(
        "INSERT INTO messages (lead_id, text, direction, source) VALUES (1, 'привет', 'in', 'Авито')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.init_db()
    database.init_db()

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT name FROM leads").fetchone()[0] == "Сохранить"
    assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1
    assert conn.execute("SELECT text FROM notes").fetchone()[0] == "заметка жива"
    assert conn.execute("SELECT text FROM messages").fetchone()[0] == "привет"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='lead_files'"
    ).fetchone()
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='leads'"
    ).fetchone()[0]
    assert "CREATE TABLE leads" in sql
    assert "DROP" not in sql.upper()
    conn.close()
