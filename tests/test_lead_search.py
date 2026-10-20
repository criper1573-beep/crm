"""Поиск GET /api/leads?q=: имя, адрес, комментарий и точный id."""

import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    db_path = tmp_path / "crm.db"
    monkeypatch.setenv("CRM_FILES_DIR", str(tmp_path / "files"))
    import backend.database as database

    monkeypatch.setattr(database, "DB_PATH", db_path)
    return db_path


@pytest.fixture()
def client(storage):
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


def _insert(db_path, lead_id, name, address="", comment="", phone="", description="", created_at="2026-01-01 00:00:00"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO leads
           (id, name, phone, address, object_type, budget, status, comment, description, created_at)
           VALUES (?, ?, ?, ?, 'Квартира', 'lo', 'lead', ?, ?, ?)""",
        (lead_id, name, phone, address, comment, description, created_at),
    )
    conn.commit()
    conn.close()


def _ids(response):
    assert response.status_code == 200, response.text
    return [row["id"] for row in response.json()]


def test_search_by_id_and_text_fields(client, storage):
    _insert(storage, 7, "Вера", comment="заявка 423", created_at="2026-08-01 00:00:00")
    _insert(storage, 8, "Глеб #423", created_at="2026-09-01 00:00:00")
    _insert(storage, 10, "423", address="дом 423", created_at="2026-10-01 00:00:00")
    _insert(storage, 11, "Пётр", phone="423000", description="423")
    _insert(storage, 423, "Борис", created_at="2020-01-01 00:00:00")
    _insert(storage, 4230, "Длинный")

    assert _ids(client.get("/api/leads")) == [7, 8, 10, 11, 423, 4230]

    assert _ids(client.get("/api/leads", params={"q": "423"})) == [423, 7, 8, 10]
    assert _ids(client.get("/api/leads", params={"q": "#423"})) == [423, 8]
    assert _ids(client.get("/api/leads", params={"q": "  #423 "})) == [423]
    assert _ids(client.get("/api/leads", params={"q": "423", "sort": "created_desc"})) == [423, 10, 8, 7]

    assert _ids(client.get("/api/leads", params={"q": "борис"})) == [423]
    assert _ids(client.get("/api/leads", params={"q": "ДОМ"})) == [10]
    assert _ids(client.get("/api/leads", params={"q": "Заявка"})) == [7]
    assert _ids(client.get("/api/leads", params={"q": "42"})) == [7, 8, 10]
    assert _ids(client.get("/api/leads", params={"q": "0423"})) == []
    assert _ids(client.get("/api/leads", params={"q": "неттакого"})) == []
    assert _ids(client.get("/api/leads", params={"q": ""})) == [7, 8, 10, 11, 423, 4230]
