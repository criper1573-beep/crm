"""Порядок GET /api/leads: без sort как раньше (по id), с sort — явный порядок."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

LEAD = {
    "name": "Тест",
    "phone": "",
    "object_type": "Квартира",
    "budget": "lo",
    "status": "lead",
}


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


def _create(client: TestClient, name: str) -> int:
    body = dict(LEAD)
    body["name"] = name
    response = client.post("/api/leads", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _set_created(db_path, lead_id: int, created_at: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE leads SET created_at = ? WHERE id = ?", (created_at, lead_id))
    conn.commit()
    conn.close()


def test_default_list_stays_ordered_by_id(client, storage):
    first = _create(client, "Старый id")
    second = _create(client, "Новый id")
    _set_created(storage, first, "2026-10-11 18:00:00")
    _set_created(storage, second, "2020-01-01 00:00:00")

    response = client.get("/api/leads")
    assert response.status_code == 200
    rows = response.json()
    ids = [row["id"] for row in rows]
    assert ids == sorted(ids)
    assert ids.index(first) < ids.index(second)
    assert "files_count" in rows[0]
    assert "created_at" in rows[0]


def test_sort_created_and_last_message(client, storage):
    older = _create(client, "Раньше")
    newer = _create(client, "Позже")
    same_a = _create(client, "Одинаково A")
    same_b = _create(client, "Одинаково B")
    quiet = _create(client, "Без сообщений")
    _set_created(storage, older, "2024-01-01 00:00:00")
    _set_created(storage, newer, "2026-06-01 00:00:00")
    _set_created(storage, same_a, "2025-05-05 12:00:00")
    _set_created(storage, same_b, "2025-05-05 12:00:00")
    _set_created(storage, quiet, "2023-03-03 00:00:00")

    client.post(
        f"/api/leads/{older}/messages/bulk",
        json=[{"text": "старое", "direction": "in", "source": "Телефон", "created_at": "2026-01-01 10:00:00"}],
    )
    client.post(
        f"/api/leads/{newer}/messages/bulk",
        json=[{"text": "свежее", "direction": "out", "source": "Телефон", "created_at": "2026-09-01 10:00:00"}],
    )
    client.post(
        f"/api/leads/{same_b}/messages/bulk",
        json=[{"text": "то же время", "direction": "in", "source": "Телефон", "created_at": "2026-08-01 10:00:00"}],
    )
    client.post(
        f"/api/leads/{same_a}/messages/bulk",
        json=[{"text": "то же время", "direction": "in", "source": "Телефон", "created_at": "2026-08-01 10:00:00"}],
    )

    desc = client.get("/api/leads?sort=created_desc")
    assert desc.status_code == 200
    desc_ids = [row["id"] for row in desc.json()]
    assert desc_ids.index(newer) < desc_ids.index(same_b) < desc_ids.index(same_a) < desc_ids.index(older)
    assert desc_ids.index(same_b) < desc_ids.index(same_a)

    asc = client.get("/api/leads?sort=created_asc")
    assert [row["id"] for row in asc.json()].index(older) < [row["id"] for row in asc.json()].index(newer)
    asc_ids = [row["id"] for row in asc.json()]
    assert asc_ids.index(same_a) < asc_ids.index(same_b)

    by_msg = client.get("/api/leads?sort=last_message")
    assert by_msg.status_code == 200
    msg_ids = [row["id"] for row in by_msg.json()]
    assert msg_ids.index(newer) < msg_ids.index(same_b) < msg_ids.index(same_a) < msg_ids.index(older)
    assert msg_ids.index(older) < msg_ids.index(quiet)

    unknown = client.get("/api/leads?sort=nope")
    assert unknown.status_code == 400

    plain = [row["id"] for row in client.get("/api/leads").json()]
    assert plain == sorted(plain)


def test_webhook_still_open(client):
    response = client.post("/api/avito/webhook", json={})
    assert response.status_code == 200
