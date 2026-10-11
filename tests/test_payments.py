"""Платежи: CRUD, идемпотентный импорт, миграция и выручка по дате поступления."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

LEAD = {
    "name": "Клиент",
    "phone": "",
    "object_type": "Квартира",
    "budget": "lo",
    "status": "client",
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


def _create(client: TestClient, name: str, status: str = "client", deal_amount: int | None = None) -> int:
    body = dict(LEAD)
    body["name"] = name
    body["status"] = status
    body["deal_amount"] = deal_amount
    response = client.post("/api/leads", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _set_created(db_path, lead_id: int, created_at: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE leads SET created_at = ? WHERE id = ?", (created_at, lead_id))
    conn.commit()
    conn.close()


def test_payment_crud_and_upsert(client):
    lead_id = _create(client, "Один", deal_amount=200000)
    other_id = _create(client, "Другой", deal_amount=1000)

    created = client.post(
        f"/api/leads/{lead_id}/payments",
        json={"paid_at": "2.12.25", "amount": 150000, "note": "Аванс", "source": "erp", "external_id": "receipt-1"},
    )
    assert created.status_code == 201, created.text
    payment = created.json()
    assert payment["paid_at"] == "2025-12-02"
    assert payment["amount"] == 150000
    assert payment["source"] == "erp"
    assert payment["external_id"] == "receipt-1"
    assert payment["lead_id"] == lead_id

    again = client.post(
        f"/api/leads/{lead_id}/payments",
        json={"paid_at": "2025-12-03", "amount": 180000, "note": "Уточнение", "source": "erp", "external_id": "receipt-1"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["id"] == payment["id"]
    assert again.json()["amount"] == 180000
    assert again.json()["paid_at"] == "2025-12-03"

    moved = client.post(
        f"/api/leads/{other_id}/payments",
        json={"paid_at": "2025-12-03", "amount": 180000, "note": "Уточнение", "source": "erp", "external_id": "receipt-1"},
    )
    assert moved.status_code == 200
    assert moved.json()["id"] == payment["id"]
    assert moved.json()["lead_id"] == other_id
    assert client.get(f"/api/leads/{lead_id}/payments").json() == []

    manual_a = client.post(f"/api/leads/{lead_id}/payments", json={"paid_at": "2026-01-02", "amount": 10, "note": ""})
    manual_b = client.post(f"/api/leads/{lead_id}/payments", json={"paid_at": "2026-01-03", "amount": 20, "note": "ещё"})
    assert manual_a.status_code == 201
    assert manual_b.status_code == 201
    assert manual_a.json()["id"] != manual_b.json()["id"]
    assert manual_a.json()["source"] == "manual"
    assert manual_a.json()["external_id"] is None

    updated = client.put(
        f"/api/leads/{lead_id}/payments/{manual_b.json()['id']}",
        json={"paid_at": "03.01.2026", "amount": 25, "note": "правлено"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["amount"] == 25
    assert updated.json()["paid_at"] == "2026-01-03"
    assert updated.json()["note"] == "правлено"

    listed = client.get(f"/api/leads/{lead_id}/payments")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [manual_b.json()["id"], manual_a.json()["id"]]

    lead = client.get(f"/api/leads/{lead_id}")
    assert lead.status_code == 200
    assert [row["id"] for row in lead.json()["payments"]] == [manual_b.json()["id"], manual_a.json()["id"]]

    assert client.delete(f"/api/leads/{lead_id}/payments/{manual_a.json()['id']}").status_code == 200
    assert client.delete(f"/api/leads/{lead_id}/payments/{manual_a.json()['id']}").status_code == 404
    assert client.post(f"/api/leads/999999/payments", json={"paid_at": "2026-01-01", "amount": 1}).status_code == 404
    assert client.post(f"/api/leads/{lead_id}/payments", json={"paid_at": "32.13.25", "amount": 1}).status_code == 400

    foreign = client.post("/api/leads", json={**LEAD, "name": "Чужой", "has_multiple_objects": True}).json()
    obj = client.post(f"/api/leads/{foreign['id']}/objects", json={"name": "Чужой объект"}).json()
    bad_object = client.post(
        f"/api/leads/{lead_id}/payments",
        json={"paid_at": "2026-02-01", "amount": 5, "object_id": obj["id"]},
    )
    assert bad_object.status_code == 400

    assert client.delete(f"/api/leads/{other_id}").status_code == 200
    assert client.get(f"/api/leads/{other_id}/payments").status_code == 404


def test_revenue_follows_payment_dates(client, storage):
    imported = _create(client, "Импорт", deal_amount=500000)
    fresh = _create(client, "Новый", deal_amount=50000)
    repeat = _create(client, "Повтор", status="repeat", deal_amount=80000)
    september = _create(client, "Сентябрь", deal_amount=1000)
    _set_created(storage, imported, "2026-10-11 09:00:00")
    _set_created(storage, fresh, "2026-10-10 09:00:00")
    _set_created(storage, repeat, "2024-01-01 00:00:00")
    _set_created(storage, september, "2026-09-15 00:00:00")

    assert client.post(
        f"/api/leads/{imported}/payments",
        json={"paid_at": "2026-04-15", "amount": 100000, "source": "erp", "external_id": "apr"},
    ).status_code == 201
    assert client.post(
        f"/api/leads/{imported}/payments",
        json={"paid_at": "2026-08-01", "amount": 200000, "source": "erp", "external_id": "aug"},
    ).status_code == 201
    assert client.post(
        f"/api/leads/{repeat}/payments",
        json={"paid_at": "2026-10-08", "amount": 70000, "source": "manual"},
    ).status_code == 201

    week = client.get("/api/analytics/revenue", params={"period": "week", "today": "2026-10-11"})
    assert week.status_code == 200, week.text
    assert week.json()["start"] == "2026-10-05"
    assert week.json()["end"] == "2026-10-11"
    assert week.json()["revenue"] == 70000
    assert week.json()["clients"] == 1
    assert week.json()["repeats"] == 1
    assert week.json()["deal_amount"] == 130000

    month = client.get("/api/analytics/revenue", params={"period": "month", "today": "2026-10-11"})
    assert month.json()["start"] == "2026-09-12"
    assert month.json()["revenue"] == 70000

    prev = client.get("/api/analytics/revenue", params={"period": "prev_month", "today": "2026-10-11"})
    assert prev.json()["start"] == "2026-09-01"
    assert prev.json()["end"] == "2026-09-30"
    assert prev.json()["revenue"] == 0
    assert prev.json()["clients"] == 1
    assert prev.json()["deal_amount"] == 1000

    august = client.get(
        "/api/analytics/revenue",
        params={"period": "custom", "start": "2026-08-01", "end": "2026-08-31", "today": "2026-10-11"},
    )
    assert august.json()["revenue"] == 200000
    assert august.json()["clients"] == 1
    assert august.json()["repeats"] == 0
    assert august.json()["deal_amount"] == 500000

    quarter = client.get("/api/analytics/revenue", params={"period": "quarter", "today": "2026-10-11"})
    assert quarter.json()["start"] == "2026-07-14"
    assert quarter.json()["end"] == "2026-10-11"
    year = client.get("/api/analytics/revenue", params={"period": "year", "today": "2026-10-11"})
    assert year.json()["start"] == "2025-10-12"
    assert year.json()["end"] == "2026-10-11"
    january = client.get("/api/analytics/revenue", params={"period": "prev_month", "today": "2026-01-15"})
    assert january.json()["start"] == "2025-12-01"
    assert january.json()["end"] == "2025-12-31"

    assert client.get("/api/analytics/revenue", params={"period": "nope"}).status_code == 400

    rows = client.get("/api/leads").json()
    imported_row = next(row for row in rows if row["id"] == imported)
    assert len(imported_row["payments"]) == 2
    assert [row["id"] for row in rows] == sorted(row["id"] for row in rows)


def test_payments_table_migrates_existing_db(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("INSERT INTO leads (name) VALUES ('Старый')")
    conn.commit()
    conn.close()

    import backend.database as database

    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.init_db()

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "payments" in tables
    assert conn.execute("SELECT name FROM leads WHERE id = 1").fetchone()[0] == "Старый"
    conn.execute(
        "INSERT INTO payments (lead_id, paid_at, amount, note, source, external_id) VALUES (1, '2026-01-01', 10, '', 'erp', 'r1')"
    )
    conn.execute(
        "INSERT INTO payments (lead_id, paid_at, amount, note, source, external_id) VALUES (1, '2026-01-02', 11, '', 'manual', NULL)"
    )
    conn.execute(
        "INSERT INTO payments (lead_id, paid_at, amount, note, source, external_id) VALUES (1, '2026-01-03', 12, '', 'manual', NULL)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO payments (lead_id, paid_at, amount, note, source, external_id) VALUES (1, '2026-01-04', 13, '', 'erp', 'r1')"
        )
    conn.close()
