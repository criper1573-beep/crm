# SQLite logic

import sqlite3
from pathlib import Path

from backend.models import Lead

# Путь к БД относительно корня проекта
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "crm.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создаёт таблицу leads при первом запуске, если её нет."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                avito_link TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                object_type TEXT NOT NULL,
                budget TEXT NOT NULL,
                status TEXT NOT NULL,
                last_contact TEXT NOT NULL DEFAULT '',
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Преобразует SQLite Row в обычный словарь."""
    return dict(row)


def get_all_leads() -> list[dict]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, name, phone, avito_link, address, object_type, budget, status, last_contact, comment, created_at FROM leads ORDER BY id"
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def get_lead_by_id(lead_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, name, phone, avito_link, address, object_type, budget, status, last_contact, comment, created_at FROM leads WHERE id = ?",
            (lead_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


def create_lead(lead: Lead) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO leads (name, phone, avito_link, address, object_type, budget, status, last_contact, comment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lead.name,
                lead.phone,
                lead.avito_link,
                lead.address,
                lead.object_type,
                lead.budget,
                lead.status,
                lead.last_contact,
                lead.comment,
            ),
        )
        conn.commit()
        return cur.lastrowid


def update_lead(lead_id: int, lead: Lead) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE leads SET
                name = ?, phone = ?, avito_link = ?, address = ?, object_type = ?, budget = ?, status = ?,
                last_contact = ?, comment = ?
               WHERE id = ?""",
            (
                lead.name,
                lead.phone,
                lead.avito_link,
                lead.address,
                lead.object_type,
                lead.budget,
                lead.status,
                lead.last_contact,
                lead.comment,
                lead_id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_lead(lead_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
        return cur.rowcount > 0
