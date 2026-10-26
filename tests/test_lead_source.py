"""Источник лида, обязательная причина отказа, отчёт и бэкфилл."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.lead_source import (
    apply_backfill_plan,
    format_backfill_plan,
    guess_source,
    read_backfill_plan,
)

LEAD = {
    "name": "Клиент",
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


def _body(**extra) -> dict:
    data = dict(LEAD)
    data.update(extra)
    return data


def test_source_roundtrip_and_omitted_put_keeps_it(client):
    created = client.post("/api/leads", json=_body(source="Авито", rejection_reason=None))
    assert created.status_code == 200, created.text
    lead = created.json()
    assert lead["source"] == "avito"
    assert lead["rejection_reason"] == ""

    renamed = client.put(f"/api/leads/{lead['id']}", json=_body(name="Новое имя"))
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["source"] == "avito"
    assert renamed.json()["name"] == "Новое имя"

    cleared = client.put(f"/api/leads/{lead['id']}", json=_body(source=""))
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["source"] == ""

    unknown = client.post("/api/leads", json=_body(source="instagram"))
    assert unknown.status_code == 400
    assert unknown.json()["detail"] == "Unknown source"


def test_drain_requires_reason_on_create_and_transition(client):
    missing = client.post("/api/leads", json=_body(status="drain_mql"))
    assert missing.status_code == 400
    assert missing.json()["detail"] == "rejection_reason is required"

    other = client.post("/api/leads", json=_body(status="drain_sql", rejection_reason="other"))
    assert other.status_code == 400
    assert other.json()["detail"] == "comment is required when rejection_reason is other"

    created = client.post(
        "/api/leads",
        json=_body(status="drain_hot", rejection_reason="price", comment="нашли дешевле"),
    )
    assert created.status_code == 200, created.text
    assert created.json()["rejection_reason"] == "price"

    lead = client.post("/api/leads", json=_body(source="telegram")).json()
    moved = client.put(f"/api/leads/{lead['id']}", json=_body(status="drain_sql", source="telegram"))
    assert moved.status_code == 400
    assert moved.json()["detail"] == "rejection_reason is required"

    ok = client.put(
        f"/api/leads/{lead['id']}",
        json=_body(status="drain_sql", source="Telegram", rejection_reason="сроки"),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["source"] == "telegram"
    assert ok.json()["rejection_reason"] == "timing"

    explained = client.put(
        f"/api/leads/{lead['id']}",
        json=_body(status="drain_sql", rejection_reason="other", comment="уехал в другой город"),
    )
    assert explained.status_code == 200, explained.text
    assert explained.json()["comment"] == "уехал в другой город"

    wiped = client.put(
        f"/api/leads/{lead['id']}",
        json=_body(status="drain_sql", rejection_reason="", comment="уехал в другой город"),
    )
    assert wiped.status_code == 400


def test_legacy_drain_without_reason_stays_editable(client, storage):
    created = client.post("/api/leads", json=_body(name="Старый слив", status="lead")).json()
    conn = sqlite3.connect(storage)
    conn.execute(
        "UPDATE leads SET status = 'drain_mql', rejection_reason = '' WHERE id = ?",
        (created["id"],),
    )
    conn.commit()
    conn.close()

    renamed = client.put(f"/api/leads/{created['id']}", json=_body(name="Старый слив 2", status="drain_mql"))
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Старый слив 2"
    assert renamed.json()["rejection_reason"] == ""

    entered = client.post("/api/leads", json=_body(status="mql")).json()
    still = client.put(f"/api/leads/{entered['id']}", json=_body(status="drain_mql", rejection_reason=""))
    assert still.status_code == 400


def test_new_columns_do_not_drop_existing_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE leads (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            comment TEXT NOT NULL DEFAULT ''
        )"""
    )
    conn.execute("INSERT INTO leads (name, status, comment) VALUES ('Старый', 'lead', 'авито, но это комментарий')")
    conn.commit()
    conn.close()

    import backend.database as database

    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.init_db()
    database.init_db()

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT name, comment, source, rejection_reason FROM leads WHERE id = 1").fetchone()
    conn.close()
    assert row == ("Старый", "авито, но это комментарий", "", "")


def test_avito_lead_gets_source(client):
    import backend.database as database

    lead_id = database.create_avito_lead("chat-1", "Авито клиент", "https://www.avito.ru/item")
    lead = client.get(f"/api/leads/{lead_id}")
    assert lead.status_code == 200
    assert lead.json()["source"] == "avito"
    assert lead.json()["rejection_reason"] == ""


def test_source_report_uses_created_at(client, storage):
    avito = client.post("/api/leads", json=_body(name="А", source="avito", status="client")).json()
    site = client.post(
        "/api/leads",
        json=_body(name="Б", source="remontfranchiz", status="drain_mql", rejection_reason="small_volume"),
    ).json()
    empty = client.post("/api/leads", json=_body(name="В", status="repeat")).json()
    old = client.post("/api/leads", json=_body(name="Г", source="avito", status="drain_hot", rejection_reason="price")).json()

    conn = sqlite3.connect(storage)
    conn.execute("UPDATE leads SET created_at = ? WHERE id = ?", ("2026-10-10 09:00:00", avito["id"]))
    conn.execute("UPDATE leads SET created_at = ? WHERE id = ?", ("2026-10-09 09:00:00", site["id"]))
    conn.execute("UPDATE leads SET created_at = ? WHERE id = ?", ("2026-10-08 09:00:00", empty["id"]))
    conn.execute("UPDATE leads SET created_at = ? WHERE id = ?", ("2026-01-01 09:00:00", old["id"]))
    conn.commit()
    conn.close()

    report = client.get("/api/analytics/sources", params={"period": "week", "today": "2026-10-11"})
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["start"] == "2026-10-05"
    assert body["end"] == "2026-10-11"
    assert body["leads_total"] == 3
    assert body["contracts_total"] == 2
    assert body["rejections_total"] == 1
    by_source = {row["source"]: row for row in body["leads_by_source"]}
    assert by_source["avito"]["leads"] == 1
    assert by_source["avito"]["contracts"] == 1
    assert by_source["remontfranchiz"]["leads"] == 1
    assert by_source["remontfranchiz"]["contracts"] == 0
    assert by_source[""]["label"] == "не указан"
    assert by_source[""]["leads"] == 1
    assert by_source[""]["contracts"] == 1
    by_reason = {row["reason"]: row for row in body["rejections_by_reason"]}
    assert by_reason["small_volume"]["count"] == 1
    assert by_reason["price"]["count"] == 0
    assert "" not in by_reason

    everything = client.get("/api/analytics/sources", params={"period": "all", "today": "2026-10-11"})
    assert everything.json()["leads_total"] == 4
    assert everything.json()["rejections_total"] == 2
    assert client.get("/api/analytics/sources", params={"period": "nope"}).status_code == 400


def test_guess_source_is_conservative():
    assert guess_source({"comment": "пришёл с Авито"})[0] == "avito"
    assert guess_source({"comment": "не авито"})[0] is None
    assert guess_source({"comment": "повторный звонок"})[0] is None
    assert guess_source({"comment": "повторный клиент"})[0] == "repeat_client"
    assert guess_source({"description": "тендер у генподрядчика"})[0] == "tender"
    assert guess_source({"comment": "заявка с сайта ремонтфраншиз.рф"})[0] == "remontfranchiz"
    assert guess_source({"comment": "оставили заявку на flowcabinet.ru"})[0] == "flowcabinet"
    assert guess_source({}, ["написали в телеграм"])[0] == "telegram"
    assert guess_source({"tg_link": "https://t.me/ivan", "comment": ""})[0] is None
    assert guess_source({"avito_chat_id": "c1"})[0] == "avito"
    assert guess_source({"avito_link": "https://www.avito.ru/1"})[0] == "avito"
    code, _why, signals = guess_source({"avito_chat_id": "c1", "comment": "это сарафан"})
    assert code is None
    assert signals == ["avito", "referral"]
    assert guess_source({"comment": "другое"})[0] is None


def test_backfill_dry_run_and_apply_are_idempotent(storage, client):
    import backend.database as database

    database.init_db()
    conn = sqlite3.connect(storage)
    conn.execute(
        """INSERT INTO leads (name, phone, address, object_type, budget, status, comment, description, source)
           VALUES ('Иван', '', '', 'Квартира', 'lo', 'lead', 'с авито', '', '')"""
    )
    conn.execute(
        """INSERT INTO leads (name, phone, address, object_type, budget, status, comment, source)
           VALUES ('Мария', '', '', 'Квартира', 'lo', 'lead', 'и авито, и телеграм', '')"""
    )
    conn.execute(
        """INSERT INTO leads (name, phone, address, object_type, budget, status, comment, source)
           VALUES ('Пётр', '', '', 'Квартира', 'lo', 'lead', '', 'telegram')"""
    )
    conn.execute(
        """INSERT INTO notes (lead_id, text)
           SELECT id, 'заявка flowcabinet' FROM leads WHERE name = 'Иван'"""
    )
    # Иван теперь неоднозначен: комментарий авито и заметка flowcabinet.
    conn.execute(
        """INSERT INTO leads (name, phone, address, object_type, budget, status, comment, avito_chat_id, source)
           VALUES ('Олег', '', '', 'Квартира', 'lo', 'lead', '', 'chat-9', '')"""
    )
    conn.commit()

    plan = read_backfill_plan(conn)
    text = format_backfill_plan(plan, dry_run=True)
    assert "dry-run, база не изменена" in text
    assert "source=avito" in text
    names = {row["name"]: row["source"] for row in plan["updates"]}
    assert names["Олег"] == "avito"
    assert "Иван" not in names
    assert "Мария" not in names
    assert "Пётр" not in names
    assert any(row["name"] == "Иван" for row in plan["ambiguous"])
    assert any(row["name"] == "Мария" for row in plan["ambiguous"])
    assert conn.execute("SELECT source FROM leads WHERE name = 'Олег'").fetchone()[0] == ""

    applied = apply_backfill_plan(conn, plan)
    assert applied == 1
    assert conn.execute("SELECT source FROM leads WHERE name = 'Олег'").fetchone()[0] == "avito"
    assert conn.execute("SELECT comment FROM leads WHERE name = 'Иван'").fetchone()[0] == "с авито"

    again = read_backfill_plan(conn)
    assert apply_backfill_plan(conn, again) == 0
    assert not any(row["name"] == "Олег" for row in again["updates"])
    conn.close()

    from scripts.backfill_lead_source import main

    assert main(["--db", str(storage), "--dry-run"]) == 0
    assert main(["--db", str(storage), "--apply", "--dry-run"]) == 2
    missing = storage.parent / "missing.db"
    assert main(["--db", str(missing)]) == 1
