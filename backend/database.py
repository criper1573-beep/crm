# SQLite logic

import json
import sqlite3
from pathlib import Path

from backend.models import Lead, NoteCreate, MessageCreate, MessageBulkItem

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
                work_types TEXT NOT NULL DEFAULT '[]',
                description TEXT NOT NULL DEFAULT '',
                deal_amount INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Миграция: добавить колонки в существующую таблицу, если их нет
        cur = conn.execute("PRAGMA table_info(leads)")
        cols = [r[1] for r in cur.fetchall()]
        if "work_types" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN work_types TEXT NOT NULL DEFAULT '[]'")
        if "description" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if "deal_amount" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN deal_amount INTEGER")
        if "communication_done" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN communication_done INTEGER NOT NULL DEFAULT 0")
        if "extra_phones" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN extra_phones TEXT NOT NULL DEFAULT ''")
        if "max_link" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN max_link TEXT NOT NULL DEFAULT ''")
        if "tg_link" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN tg_link TEXT NOT NULL DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                direction TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Преобразует SQLite Row в обычный словарь."""
    return dict(row)


def _lead_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "work_types" in d and isinstance(d.get("work_types"), str):
        try:
            d["work_types"] = json.loads(d["work_types"]) if d["work_types"] else []
        except (json.JSONDecodeError, TypeError):
            d["work_types"] = []
    if "description" not in d:
        d["description"] = ""
    if "deal_amount" in d and d["deal_amount"] is not None:
        try:
            d["deal_amount"] = int(d["deal_amount"])
        except (TypeError, ValueError):
            d["deal_amount"] = None
    if "communication_done" not in d:
        d["communication_done"] = False
    elif d["communication_done"] is not None:
        d["communication_done"] = bool(int(d["communication_done"]))
    return d


def _get_last_message_per_lead() -> dict[int, dict]:
    """Возвращает для каждого lead_id последнее сообщение: {direction, created_at}."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT lead_id, direction, created_at FROM messages ORDER BY lead_id, created_at DESC"
        )
        rows = cur.fetchall()
    result = {}
    for r in rows:
        lead_id = r["lead_id"]
        if lead_id not in result:
            result[lead_id] = {"direction": r["direction"], "created_at": r["created_at"] or ""}
    return result


def get_all_leads() -> list[dict]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, name, phone, extra_phones, avito_link, max_link, tg_link, address, object_type, budget, status, last_contact, comment, work_types, description, deal_amount, communication_done, created_at FROM leads ORDER BY id"
        )
        leads_list = [_lead_row_to_dict(r) for r in cur.fetchall()]
    last_msgs = _get_last_message_per_lead()
    for lead in leads_list:
        lm = last_msgs.get(lead["id"], {})
        lead["last_message_direction"] = lm.get("direction") or ""
        lead["last_message_date"] = lm.get("created_at") or ""
    return leads_list


def get_lead_by_id(lead_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, name, phone, extra_phones, avito_link, max_link, tg_link, address, object_type, budget, status, last_contact, comment, work_types, description, deal_amount, communication_done, created_at FROM leads WHERE id = ?",
            (lead_id,),
        )
        row = cur.fetchone()
        return _lead_row_to_dict(row) if row else None


def create_lead(lead: Lead) -> int:
    work_types_json = json.dumps(getattr(lead, "work_types", []) or [])
    description = getattr(lead, "description", "") or ""
    comm_done = 1 if getattr(lead, "communication_done", False) else 0
    with get_connection() as conn:
        deal_amount = getattr(lead, "deal_amount", None)
        cur = conn.execute(
            """INSERT INTO leads (name, phone, extra_phones, avito_link, max_link, tg_link, address, object_type, budget, status, last_contact, comment, work_types, description, deal_amount, communication_done)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lead.name,
                lead.phone,
                getattr(lead, "extra_phones", "") or "",
                lead.avito_link,
                getattr(lead, "max_link", "") or "",
                getattr(lead, "tg_link", "") or "",
                lead.address,
                lead.object_type,
                lead.budget,
                lead.status,
                lead.last_contact,
                lead.comment,
                work_types_json,
                description,
                deal_amount,
                comm_done,
            ),
        )
        conn.commit()
        return cur.lastrowid


def update_lead(lead_id: int, lead: Lead) -> bool:
    work_types_json = json.dumps(getattr(lead, "work_types", []) or [])
    description = getattr(lead, "description", "") or ""
    deal_amount = getattr(lead, "deal_amount", None)
    comm_done = 1 if getattr(lead, "communication_done", False) else 0
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE leads SET
                name = ?, phone = ?, extra_phones = ?, avito_link = ?, max_link = ?, tg_link = ?, address = ?, object_type = ?, budget = ?, status = ?,
                last_contact = ?, comment = ?, work_types = ?, description = ?, deal_amount = ?, communication_done = ?
               WHERE id = ?""",
            (
                lead.name,
                lead.phone,
                getattr(lead, "extra_phones", "") or "",
                lead.avito_link,
                getattr(lead, "max_link", "") or "",
                getattr(lead, "tg_link", "") or "",
                lead.address,
                lead.object_type,
                lead.budget,
                lead.status,
                lead.last_contact,
                lead.comment,
                work_types_json,
                description,
                deal_amount,
                comm_done,
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


def get_notes_by_lead_id(lead_id: int) -> list[dict]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, lead_id, text, created_at FROM notes WHERE lead_id = ? ORDER BY created_at DESC",
            (lead_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def create_note(lead_id: int, note: NoteCreate) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO notes (lead_id, text) VALUES (?, ?)",
            (lead_id, note.text),
        )
        conn.commit()
        return cur.lastrowid


def get_note_by_id(note_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, lead_id, text, created_at FROM notes WHERE id = ?",
            (note_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


def delete_note(note_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
        return cur.rowcount > 0


def get_messages_by_lead_id(lead_id: int) -> list[dict]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, lead_id, text, direction, source, created_at FROM messages WHERE lead_id = ? ORDER BY created_at ASC",
            (lead_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def set_lead_communication_done(lead_id: int, value: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE leads SET communication_done = ? WHERE id = ?", (1 if value else 0, lead_id))
        conn.commit()


def create_message(lead_id: int, msg: MessageCreate) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO messages (lead_id, text, direction, source) VALUES (?, ?, ?, ?)",
            (lead_id, msg.text, msg.direction, msg.source),
        )
        conn.commit()
        if (msg.direction or "").strip().lower() == "in":
            set_lead_communication_done(lead_id, False)
        return cur.lastrowid


def create_messages_bulk(lead_id: int, items: list[MessageBulkItem]) -> list[int]:
    ids = []
    has_in = any((item.direction or "").strip().lower() == "in" for item in items)
    with get_connection() as conn:
        for item in items:
            created_at = item.created_at if item.created_at else None
            if created_at:
                cur = conn.execute(
                    "INSERT INTO messages (lead_id, text, direction, source, created_at) VALUES (?, ?, ?, ?, ?)",
                    (lead_id, item.text, item.direction, item.source, created_at),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO messages (lead_id, text, direction, source) VALUES (?, ?, ?, ?)",
                    (lead_id, item.text, item.direction, item.source),
                )
            ids.append(cur.lastrowid)
        conn.commit()
    if has_in:
        set_lead_communication_done(lead_id, False)
    return ids


def get_message_by_id(message_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, lead_id, text, direction, source, created_at FROM messages WHERE id = ?",
            (message_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


def delete_message(message_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        conn.commit()
        return cur.rowcount > 0


def update_message_direction(message_id: int, direction: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE messages SET direction = ? WHERE id = ?",
            (direction, message_id),
        )
        conn.commit()
        return cur.rowcount > 0


def _parse_date_to_ymd(s: str):
    """Парсит строку даты в (year, month, day) или None. Поддерживает разные форматы."""
    import re
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    # YYYY-MM-DD или YYYY-MM-DD HH:MM:SS или YYYY-MM-DDTHH:MM:SS
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # DD.MM.YYYY или D.M.YYYY (с пробелом/временем после)
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    # DD.MM.YY (двузначный год: 00-99 → 2000-2099)
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2})\b", s)
    if m:
        yy = int(m.group(3))
        year = 2000 + yy if yy < 100 else yy
        return (year, int(m.group(2)), int(m.group(1)))
    # DD/MM/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def sync_created_at_from_last_contact() -> int:
    """
    Проставляет created_at: из last_contact, при пустом — из даты последнего сообщения.
    Возвращает количество обновлённых записей.
    """
    with get_connection() as conn:
        cur = conn.execute("SELECT id, last_contact FROM leads")
        leads_rows = cur.fetchall()
        cur = conn.execute(
            "SELECT lead_id, MAX(created_at) AS last_msg FROM messages GROUP BY lead_id"
        )
        last_msg_by_lead = {r["lead_id"]: r["last_msg"] for r in cur.fetchall()}

        updated = 0
        for row in leads_rows:
            lead_id = row["id"]
            last_contact = (row["last_contact"] or "").strip()
            ymd = _parse_date_to_ymd(last_contact)
            if not ymd and lead_id in last_msg_by_lead:
                last_msg = last_msg_by_lead[lead_id] or ""
                ymd = _parse_date_to_ymd(last_msg)
            if not ymd:
                continue
            y, mo, d = ymd
            created_at = f"{y:04d}-{mo:02d}-{d:02d} 00:00:00"
            conn.execute("UPDATE leads SET created_at = ? WHERE id = ?", (created_at, lead_id))
            updated += 1
        conn.commit()
    return updated
