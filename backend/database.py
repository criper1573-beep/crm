# SQLite logic

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from backend.models import Lead, LeadObject, LeadObjectCreate, NoteCreate, MessageCreate, MessageBulkItem

# Путь к БД относительно корня проекта
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "crm.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Триггер updated_at сам делает UPDATE leads. Рекурсия зациклила бы его.
    conn.execute("PRAGMA recursive_triggers = OFF")
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
        if "has_multiple_objects" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN has_multiple_objects INTEGER NOT NULL DEFAULT 0")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                name TEXT NOT NULL DEFAULT 'Объект',
                address TEXT NOT NULL DEFAULT '',
                object_type TEXT NOT NULL DEFAULT 'Квартира',
                budget TEXT NOT NULL DEFAULT 'lo',
                work_types TEXT NOT NULL DEFAULT '[]',
                description TEXT NOT NULL DEFAULT '',
                deal_amount INTEGER,
                last_contact TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """)
        cur = conn.execute("PRAGMA table_info(lead_objects)")
        obj_cols = [r[1] for r in cur.fetchall()]
        if "last_contact" not in obj_cols:
            conn.execute("ALTER TABLE lead_objects ADD COLUMN last_contact TEXT NOT NULL DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cur = conn.execute("PRAGMA table_info(notes)")
        note_cols = [r[1] for r in cur.fetchall()]
        if "lead_object_id" not in note_cols:
            conn.execute("ALTER TABLE notes ADD COLUMN lead_object_id INTEGER REFERENCES lead_objects(id)")
        if "avito_chat_id" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN avito_chat_id TEXT")
        if "avito_new_chat" not in cols:
            conn.execute("ALTER TABLE leads ADD COLUMN avito_new_chat INTEGER NOT NULL DEFAULT 0")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                direction TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                avito_message_id TEXT
            )
        """)
        cur = conn.execute("PRAGMA table_info(messages)")
        msg_cols = [r[1] for r in cur.fetchall()]
        if "avito_message_id" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN avito_message_id TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                object_id INTEGER,
                paid_at TEXT NOT NULL,
                amount INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                external_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_external_id "
            "ON payments(external_id) WHERE external_id IS NOT NULL"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_lead ON payments(lead_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_paid ON payments(paid_at)")
        _ensure_change_tracking(conn)
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
    if "has_multiple_objects" not in d:
        d["has_multiple_objects"] = False
    elif d.get("has_multiple_objects") is not None:
        d["has_multiple_objects"] = bool(int(d["has_multiple_objects"]))
    if "avito_new_chat" not in d:
        d["avito_new_chat"] = False
    elif d.get("avito_new_chat") is not None:
        d["avito_new_chat"] = bool(int(d["avito_new_chat"]))
    if "avito_chat_id" not in d:
        d["avito_chat_id"] = None
    return d


def _lead_object_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "work_types" in d and isinstance(d.get("work_types"), str):
        try:
            d["work_types"] = json.loads(d["work_types"]) if d["work_types"] else []
        except (json.JSONDecodeError, TypeError):
            d["work_types"] = []
    if "deal_amount" in d and d["deal_amount"] is not None:
        try:
            d["deal_amount"] = int(d["deal_amount"])
        except (TypeError, ValueError):
            d["deal_amount"] = None
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
            "SELECT id, name, phone, extra_phones, avito_link, max_link, tg_link, address, object_type, budget, status, last_contact, comment, work_types, description, deal_amount, communication_done, has_multiple_objects, avito_chat_id, avito_new_chat, created_at FROM leads ORDER BY id"
        )
        leads_list = [_lead_row_to_dict(r) for r in cur.fetchall()]
    last_msgs = _get_last_message_per_lead()
    for lead in leads_list:
        lm = last_msgs.get(lead["id"], {})
        lead["last_message_direction"] = lm.get("direction") or ""
        lead["last_message_date"] = lm.get("created_at") or ""
        if lead.get("has_multiple_objects"):
            objs = get_objects_by_lead_id(lead["id"])
            lead["objects"] = objs
            lead["effective_deal_amount"] = sum((o.get("deal_amount") or 0) for o in objs)
        else:
            lead["objects"] = []
            lead["effective_deal_amount"] = lead.get("deal_amount") or 0
    grouped: dict[int, list[dict]] = {}
    for payment in list_payments():
        grouped.setdefault(payment["lead_id"], []).append(payment)
    for lead in leads_list:
        lead["payments"] = grouped.get(lead["id"], [])
    return leads_list


_ISO_STAMP = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?")
LEAD_SORTS = ("created_desc", "created_asc", "last_message")


def _lead_stamp(value: str | None) -> str:
    raw = (value or "").strip()
    match = _ISO_STAMP.match(raw)
    if not match:
        return ""
    hh = match.group(4) or "00"
    mm = match.group(5) or "00"
    ss = match.group(6) or "00"
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)} {hh}:{mm}:{ss}"


def sort_leads(leads: list[dict], mode: str) -> list[dict]:
    """Порядок списка. Не меняет записи, только возвращает новый список.

    created_desc — created_at по убыванию, при равенстве id по убыванию.
    created_asc — created_at по возрастанию, при равенстве id по возрастанию.
    last_message — дата последнего сообщения по убыванию; без сообщений в конце.
    """
    rows = list(leads)

    def lead_id(lead: dict) -> int:
        try:
            return int(lead.get("id") or 0)
        except (TypeError, ValueError):
            return 0

    if mode == "created_desc":
        rows.sort(key=lambda lead: (_lead_stamp(lead.get("created_at")), lead_id(lead)), reverse=True)
    elif mode == "created_asc":
        rows.sort(key=lambda lead: (_lead_stamp(lead.get("created_at")) or "9999-99-99 99:99:99", lead_id(lead)))
    elif mode == "last_message":
        rows.sort(key=lambda lead: (_lead_stamp(lead.get("last_message_date")), lead_id(lead)), reverse=True)
    else:
        raise ValueError(mode)
    return rows


def get_lead_by_id(lead_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, name, phone, extra_phones, avito_link, max_link, tg_link, address, object_type, budget, status, last_contact, comment, work_types, description, deal_amount, communication_done, has_multiple_objects, avito_chat_id, avito_new_chat, created_at FROM leads WHERE id = ?",
            (lead_id,),
        )
        row = cur.fetchone()
        return _lead_row_to_dict(row) if row else None


def create_lead(lead: Lead) -> int:
    work_types_json = json.dumps(getattr(lead, "work_types", []) or [])
    description = getattr(lead, "description", "") or ""
    comm_done = 1 if getattr(lead, "communication_done", False) else 0
    has_multi = 1 if getattr(lead, "has_multiple_objects", False) else 0
    avito_chat_id = getattr(lead, "avito_chat_id", None)
    avito_new_chat = 1 if getattr(lead, "avito_new_chat", False) else 0
    with get_connection() as conn:
        deal_amount = getattr(lead, "deal_amount", None)
        cur = conn.execute(
            """INSERT INTO leads (name, phone, extra_phones, avito_link, max_link, tg_link, address, object_type, budget, status, last_contact, comment, work_types, description, deal_amount, communication_done, has_multiple_objects, avito_chat_id, avito_new_chat)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                has_multi,
                avito_chat_id,
                avito_new_chat,
            ),
        )
        conn.commit()
        return cur.lastrowid


def update_lead(lead_id: int, lead: Lead) -> bool:
    work_types_json = json.dumps(getattr(lead, "work_types", []) or [])
    description = getattr(lead, "description", "") or ""
    deal_amount = getattr(lead, "deal_amount", None)
    comm_done = 1 if getattr(lead, "communication_done", False) else 0
    has_multi = 1 if getattr(lead, "has_multiple_objects", False) else 0
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE leads SET
                name = ?, phone = ?, extra_phones = ?, avito_link = ?, max_link = ?, tg_link = ?, address = ?, object_type = ?, budget = ?, status = ?,
                last_contact = ?, comment = ?, work_types = ?, description = ?, deal_amount = ?, communication_done = ?, has_multiple_objects = ?
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
                has_multi,
                lead_id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_lead(lead_id: int) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM payments WHERE lead_id = ?", (lead_id,))
        cur = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
        return cur.rowcount > 0


def get_objects_by_lead_id(lead_id: int) -> list[dict]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, lead_id, name, address, object_type, budget, work_types, description, deal_amount, last_contact, sort_order FROM lead_objects WHERE lead_id = ? ORDER BY sort_order, id",
            (lead_id,),
        )
        return [_lead_object_row_to_dict(r) for r in cur.fetchall()]


def get_object_by_id(object_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, lead_id, name, address, object_type, budget, work_types, description, deal_amount, last_contact, sort_order FROM lead_objects WHERE id = ?",
            (object_id,),
        )
        row = cur.fetchone()
        return _lead_object_row_to_dict(row) if row else None


def create_lead_object(lead_id: int, obj: LeadObjectCreate) -> int:
    work_types_json = json.dumps(getattr(obj, "work_types", []) or [])
    last_contact = getattr(obj, "last_contact", "") or ""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO lead_objects (lead_id, name, address, object_type, budget, work_types, description, deal_amount, last_contact, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lead_id,
                obj.name or "Объект",
                obj.address or "",
                obj.object_type or "Квартира",
                obj.budget or "lo",
                work_types_json,
                obj.description or "",
                obj.deal_amount,
                last_contact,
                getattr(obj, "sort_order", 0) or 0,
            ),
        )
        conn.commit()
        return cur.lastrowid


def update_lead_object(object_id: int, obj: LeadObjectCreate | dict) -> bool:
    if isinstance(obj, dict):
        name = obj.get("name", "Объект")
        address = obj.get("address", "")
        object_type = obj.get("object_type", "Квартира")
        budget = obj.get("budget", "lo")
        work_types = obj.get("work_types", [])
        description = obj.get("description", "")
        deal_amount = obj.get("deal_amount")
        last_contact = obj.get("last_contact", "")
        sort_order = obj.get("sort_order", 0)
    else:
        name = obj.name or "Объект"
        address = obj.address or ""
        object_type = obj.object_type or "Квартира"
        budget = obj.budget or "lo"
        work_types = getattr(obj, "work_types", []) or []
        description = obj.description or ""
        deal_amount = obj.deal_amount
        last_contact = getattr(obj, "last_contact", "") or ""
        sort_order = getattr(obj, "sort_order", 0) or 0
    work_types_json = json.dumps(work_types) if isinstance(work_types, list) else work_types
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE lead_objects SET name = ?, address = ?, object_type = ?, budget = ?, work_types = ?, description = ?, deal_amount = ?, last_contact = ?, sort_order = ? WHERE id = ?""",
            (name, address, object_type, budget, work_types_json, description, deal_amount, last_contact, sort_order, object_id),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_lead_object(object_id: int) -> bool:
    with get_connection() as conn:
        conn.execute("UPDATE notes SET lead_object_id = NULL WHERE lead_object_id = ?", (object_id,))
        conn.execute("UPDATE payments SET object_id = NULL WHERE object_id = ?", (object_id,))
        cur = conn.execute("DELETE FROM lead_objects WHERE id = ?", (object_id,))
        conn.commit()
        return cur.rowcount > 0


def migrate_lead_to_first_object(lead_id: int) -> int | None:
    """Создаёт первый объект из данных лида и привязывает к нему заметки. Возвращает id созданного объекта или None."""
    lead = get_lead_by_id(lead_id)
    if not lead:
        return None
    with get_connection() as conn:
        work_types_json = lead.get("work_types") or []
        if isinstance(work_types_json, list):
            work_types_json = json.dumps(work_types_json)
        cur = conn.execute(
            """INSERT INTO lead_objects (lead_id, name, address, object_type, budget, work_types, description, deal_amount, last_contact, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                lead_id,
                "Объект 1",
                lead.get("address") or "",
                lead.get("object_type") or "Квартира",
                lead.get("budget") or "lo",
                work_types_json,
                lead.get("description") or "",
                lead.get("deal_amount"),
                lead.get("last_contact") or "",
            ),
        )
        obj_id = cur.lastrowid
        conn.execute("UPDATE notes SET lead_object_id = ? WHERE lead_id = ? AND (lead_object_id IS NULL OR lead_object_id = 0)", (obj_id, lead_id))
        conn.commit()
    return obj_id


def get_notes_by_lead_id(lead_id: int, lead_object_id: int | None = None) -> list[dict]:
    with get_connection() as conn:
        if lead_object_id is not None:
            cur = conn.execute(
                "SELECT id, lead_id, lead_object_id, text, created_at FROM notes WHERE lead_id = ? AND lead_object_id = ? ORDER BY created_at DESC",
                (lead_id, lead_object_id),
            )
        else:
            cur = conn.execute(
                "SELECT id, lead_id, lead_object_id, text, created_at FROM notes WHERE lead_id = ? AND (lead_object_id IS NULL OR lead_object_id = 0) ORDER BY created_at DESC",
                (lead_id,),
            )
        rows = cur.fetchall()
    return [_row_to_dict(r) for r in rows]


def create_note(lead_id: int, note: NoteCreate, lead_object_id: int | None = None) -> int:
    obj_id = getattr(note, "lead_object_id", None) or lead_object_id
    with get_connection() as conn:
        if obj_id is not None:
            cur = conn.execute(
                "INSERT INTO notes (lead_id, lead_object_id, text) VALUES (?, ?, ?)",
                (lead_id, obj_id, note.text),
            )
        else:
            cur = conn.execute(
                "INSERT INTO notes (lead_id, text) VALUES (?, ?)",
                (lead_id, note.text),
            )
        conn.commit()
        return cur.lastrowid


def get_note_by_id(note_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, lead_id, lead_object_id, text, created_at FROM notes WHERE id = ?",
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
            "SELECT id, lead_id, text, direction, source, created_at, avito_message_id FROM messages WHERE lead_id = ? ORDER BY created_at ASC",
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
            "SELECT id, lead_id, text, direction, source, created_at, avito_message_id FROM messages WHERE id = ?",
            (message_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


def delete_message(message_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        conn.commit()
        return cur.rowcount > 0


def get_lead_by_avito_chat_id(avito_chat_id: str) -> dict | None:
    """Найти лид по ID чата Авито."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, name, phone, extra_phones, avito_link, max_link, tg_link, address, object_type, budget, status, last_contact, comment, work_types, description, deal_amount, communication_done, has_multiple_objects, avito_chat_id, avito_new_chat, created_at FROM leads WHERE avito_chat_id = ?",
            (avito_chat_id,),
        )
        row = cur.fetchone()
        return _lead_row_to_dict(row) if row else None


def create_avito_lead(avito_chat_id: str, name: str = "", avito_link: str = "") -> int:
    """Создать новый лид из чата Авито с флагом avito_new_chat=1."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO leads (name, phone, avito_link, address, object_type, budget, status,
               work_types, description, communication_done, has_multiple_objects,
               avito_chat_id, avito_new_chat)
               VALUES (?, '', ?, '', 'Квартира', 'lo', 'lead', '[]', '', 0, 0, ?, 1)""",
            (name or "Авито клиент", avito_link or "", avito_chat_id),
        )
        conn.commit()
        return cur.lastrowid


def avito_message_exists(avito_message_id: str) -> bool:
    """Проверить, есть ли уже сообщение с таким avito_message_id (дедупликация)."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id FROM messages WHERE avito_message_id = ?",
            (avito_message_id,),
        )
        return cur.fetchone() is not None


def create_avito_message(
    lead_id: int,
    text: str,
    direction: str,
    created_at: str | None,
    avito_message_id: str,
) -> int | None:
    """Вставить сообщение из Авито с дедупликацией по avito_message_id.
    Возвращает id созданного сообщения или None если уже существует."""
    if avito_message_exists(avito_message_id):
        return None
    with get_connection() as conn:
        if created_at:
            cur = conn.execute(
                "INSERT INTO messages (lead_id, text, direction, source, created_at, avito_message_id) VALUES (?, ?, ?, 'Авито', ?, ?)",
                (lead_id, text, direction, created_at, avito_message_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO messages (lead_id, text, direction, source, avito_message_id) VALUES (?, ?, ?, 'Авито', ?)",
                (lead_id, text, direction, avito_message_id),
            )
        conn.commit()
    if direction == "in":
        set_lead_communication_done(lead_id, False)
    return cur.lastrowid


def set_lead_avito_new_chat(lead_id: int, value: bool) -> None:
    """Установить/сбросить флаг avito_new_chat у лида."""
    with get_connection() as conn:
        conn.execute("UPDATE leads SET avito_new_chat = ? WHERE id = ?", (1 if value else 0, lead_id))
        conn.commit()


def update_lead_avito_info(lead_id: int, name: str | None = None, avito_link: str | None = None) -> None:
    """Обновить имя/ссылку лида из данных чата Авито (только если поле пустое/плейсхолдер)."""
    with get_connection() as conn:
        if name:
            conn.execute(
                "UPDATE leads SET name = ? WHERE id = ? AND name IN ('Авито клиент', '')",
                (name, lead_id),
            )
        if avito_link:
            conn.execute(
                "UPDATE leads SET avito_link = ? WHERE id = ? AND avito_link = ''",
                (avito_link, lead_id),
            )
        conn.commit()


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


class PaymentError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _to_ymd(value: str | None) -> str:
    parsed = _parse_date_to_ymd(value or "")
    if not parsed:
        return ""
    year, month, day = parsed
    try:
        from datetime import date
        date(year, month, day)
    except ValueError:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def _payment_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["amount"] = int(item["amount"])
    if item.get("object_id") is not None:
        item["object_id"] = int(item["object_id"])
    if not item.get("external_id"):
        item["external_id"] = None
    return item


def list_payments(lead_id: int | None = None) -> list[dict]:
    with get_connection() as conn:
        if lead_id is None:
            cur = conn.execute(
                "SELECT id, lead_id, object_id, paid_at, amount, note, source, external_id, created_at "
                "FROM payments ORDER BY paid_at DESC, id DESC"
            )
        else:
            cur = conn.execute(
                "SELECT id, lead_id, object_id, paid_at, amount, note, source, external_id, created_at "
                "FROM payments WHERE lead_id = ? ORDER BY paid_at DESC, id DESC",
                (lead_id,),
            )
        return [_payment_row(row) for row in cur.fetchall()]


def get_payment(payment_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, lead_id, object_id, paid_at, amount, note, source, external_id, created_at "
            "FROM payments WHERE id = ?",
            (payment_id,),
        )
        row = cur.fetchone()
        return _payment_row(row) if row else None


def _clean_external_id(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_object(lead_id: int, object_id: int | None) -> int | None:
    if object_id in (None, 0, ""):
        return None
    try:
        object_id = int(object_id)
    except (TypeError, ValueError):
        raise PaymentError("bad_object")
    obj = get_object_by_id(object_id)
    if obj is None or obj.get("lead_id") != lead_id:
        raise PaymentError("bad_object")
    return object_id


def save_payment(lead_id: int, payload: dict, payment_id: int | None = None) -> tuple[dict, bool]:
    """Создаёт платёж или обновляет существующий. Возвращает (платёж, created).

    POST с уже известным external_id обновляет ту же строку (идемпотентный импорт),
    в том числе переносит её на lead_id из URL.
    """
    current = None
    if payment_id is not None:
        current = get_payment(payment_id)
        if current is None or current["lead_id"] != lead_id:
            raise PaymentError("not_found")

    if "paid_at" in payload and payload.get("paid_at") is not None:
        paid_at = _to_ymd(str(payload.get("paid_at")))
        if not paid_at:
            raise PaymentError("bad_date")
    elif current is not None:
        paid_at = current["paid_at"]
    else:
        raise PaymentError("bad_date")

    if "amount" in payload and payload.get("amount") is not None:
        try:
            amount = int(payload.get("amount"))
        except (TypeError, ValueError):
            raise PaymentError("bad_amount")
    elif current is not None:
        amount = current["amount"]
    else:
        raise PaymentError("bad_amount")

    if "note" in payload and payload.get("note") is not None:
        note = str(payload.get("note") or "")
    elif current is not None:
        note = current["note"]
    else:
        note = ""

    if "source" in payload and payload.get("source") is not None:
        source = str(payload.get("source"))
    elif current is not None:
        source = current["source"]
    else:
        source = "manual"
    if source not in ("manual", "erp"):
        raise PaymentError("bad_source")

    if "object_id" in payload:
        object_id = _require_object(lead_id, payload.get("object_id"))
    elif current is not None:
        object_id = _require_object(lead_id, current.get("object_id"))
    else:
        object_id = None

    if "external_id" in payload:
        external_id = _clean_external_id(payload.get("external_id"))
    elif current is not None:
        external_id = current.get("external_id")
    else:
        external_id = None

    with get_connection() as conn:
        if external_id:
            other = conn.execute(
                "SELECT id FROM payments WHERE external_id = ?",
                (external_id,),
            ).fetchone()
            if other is not None and (current is None or other["id"] != current["id"]):
                if current is not None:
                    raise PaymentError("duplicate_external")
                current = get_payment(other["id"])
                payment_id = other["id"]

        if current is not None:
            conn.execute(
                """UPDATE payments
                   SET lead_id = ?, object_id = ?, paid_at = ?, amount = ?, note = ?, source = ?, external_id = ?
                   WHERE id = ?""",
                (lead_id, object_id, paid_at, amount, note, source, external_id, payment_id),
            )
            conn.commit()
            created = False
            saved_id = payment_id
        else:
            try:
                cur = conn.execute(
                    """INSERT INTO payments (lead_id, object_id, paid_at, amount, note, source, external_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (lead_id, object_id, paid_at, amount, note, source, external_id),
                )
                conn.commit()
                created = True
                saved_id = cur.lastrowid
            except sqlite3.IntegrityError:
                conn.rollback()
                other = conn.execute(
                    "SELECT id FROM payments WHERE external_id = ?",
                    (external_id,),
                ).fetchone()
                if other is None or not external_id:
                    raise
                conn.execute(
                    """UPDATE payments
                       SET lead_id = ?, object_id = ?, paid_at = ?, amount = ?, note = ?, source = ?, external_id = ?
                       WHERE id = ?""",
                    (lead_id, object_id, paid_at, amount, note, source, external_id, other["id"]),
                )
                conn.commit()
                created = False
                saved_id = other["id"]
    saved = get_payment(saved_id)
    if saved is None:
        raise PaymentError("not_found")
    return saved, created


def delete_payment(lead_id: int, payment_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM payments WHERE id = ? AND lead_id = ?",
            (payment_id, lead_id),
        )
        conn.commit()
        return cur.rowcount > 0


PERIODS = ("week", "month", "prev_month", "quarter", "year", "all", "custom")
_PERIOD_ALIASES = {"7": "week", "30": "month", "90": "quarter"}


def canonical_period(period: str | None) -> str:
    key = (period or "").strip()
    if key in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[key]
    if key in PERIODS:
        return key
    return "month"


def known_period(period: str | None) -> bool:
    key = (period or "").strip()
    return key in PERIODS or key in _PERIOD_ALIASES


def period_range(period: str | None, start: str | None, end: str | None, today: str) -> tuple[str, str]:
    """Границы периода включительно. week/month/quarter/year — последние 7/30/90/365 дней."""
    from datetime import date, timedelta

    key = canonical_period(period)
    today_ymd = _to_ymd(today) or date.today().isoformat()
    today_date = date.fromisoformat(today_ymd)
    if key == "all":
        return "", ""
    if key == "week":
        return (today_date - timedelta(days=6)).isoformat(), today_ymd
    if key == "month":
        return (today_date - timedelta(days=29)).isoformat(), today_ymd
    if key == "quarter":
        return (today_date - timedelta(days=89)).isoformat(), today_ymd
    if key == "year":
        return (today_date - timedelta(days=364)).isoformat(), today_ymd
    if key == "prev_month":
        first_this = today_date.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev.isoformat(), last_prev.isoformat()
    range_start = _to_ymd(start or "")
    range_end = _to_ymd(end or "")
    if range_start and range_end and range_start > range_end:
        range_start, range_end = range_end, range_start
    return range_start, range_end


def _in_range(ymd: str, start: str, end: str) -> bool:
    if not ymd:
        return False
    if start and ymd < start:
        return False
    if end and ymd > end:
        return False
    return True


def counts_in_period(lead: dict, start: str, end: str) -> bool:
    """Клиент/повторно: есть платёж в периоде, либо лид создан в периоде и платежей нет.

    Импорт с уже записанными старыми платежами не считается новым клиентом периода,
    даже если created_at попадает в этот период.
    """
    if lead.get("status") not in ("client", "repeat"):
        return False
    payments = lead.get("payments") or []
    if any(_in_range(_to_ymd(item.get("paid_at")), start, end) for item in payments):
        return True
    if payments:
        return False
    return _in_range(_to_ymd(lead.get("created_at")), start, end)


def analytics_summary(period: str | None, start: str | None, end: str | None, today: str) -> dict:
    range_start, range_end = period_range(period, start, end, today)
    revenue = 0
    deal_amount = 0
    clients = 0
    repeats = 0
    for lead in get_all_leads():
        for payment in lead.get("payments") or []:
            if _in_range(_to_ymd(payment.get("paid_at")), range_start, range_end):
                revenue += int(payment.get("amount") or 0)
        if not counts_in_period(lead, range_start, range_end):
            continue
        deal_amount += int(lead.get("effective_deal_amount") or 0)
        if lead.get("status") == "client":
            clients += 1
        elif lead.get("status") == "repeat":
            repeats += 1
    return {
        "period": canonical_period(period),
        "start": range_start,
        "end": range_end,
        "revenue": revenue,
        "deal_amount": deal_amount,
        "clients": clients,
        "repeats": repeats,
    }


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


_TOUCH_TABLES = ("notes", "lead_objects", "messages", "payments")
EXPORT_RELATIONS = ("notes", "objects", "messages", "files", "payments")
_SINCE_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2})(?::(\d{2}))?)?$"
)


def _install_touch_triggers(conn: sqlite3.Connection, table: str) -> None:
    """Любое изменение вложенной строки двигает leads.updated_at. Рекурсия выключена."""
    for action, suffix, lead_ref in (
        ("INSERT", "ins", "NEW.lead_id"),
        ("UPDATE", "upd", "NEW.lead_id"),
        ("DELETE", "del", "OLD.lead_id"),
    ):
        conn.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_{suffix}_touch
            AFTER {action} ON {table}
            BEGIN
                UPDATE leads SET updated_at = datetime('now') WHERE id = {lead_ref};
            END
            """
        )


def _ensure_change_tracking(conn: sqlite3.Connection) -> None:
    """Аддитивно: leads.updated_at и триггеры. Существующие строки не переписываются, если штамп уже есть."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(leads)")]
    if "updated_at" not in cols:
        conn.execute("ALTER TABLE leads ADD COLUMN updated_at TEXT")
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_leads_set_updated
        AFTER UPDATE ON leads
        WHEN NEW.updated_at IS OLD.updated_at
        BEGIN
            UPDATE leads SET updated_at = datetime('now') WHERE id = NEW.id;
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_leads_set_updated_ins
        AFTER INSERT ON leads
        WHEN NEW.updated_at IS NULL
        BEGIN
            UPDATE leads SET updated_at = datetime('now') WHERE id = NEW.id;
        END
        """
    )
    for table in _TOUCH_TABLES:
        _install_touch_triggers(conn, table)
    if "created_at" in cols:
        conn.execute(
            """
            UPDATE leads
            SET updated_at = COALESCE(NULLIF((
                SELECT MAX(ts) FROM (
                    SELECT created_at AS ts FROM leads AS self WHERE self.id = leads.id
                    UNION ALL
                    SELECT created_at FROM notes WHERE lead_id = leads.id
                    UNION ALL
                    SELECT created_at FROM messages WHERE lead_id = leads.id
                    UNION ALL
                    SELECT created_at FROM payments WHERE lead_id = leads.id
                )
            ), ''), datetime('now'))
            WHERE updated_at IS NULL OR updated_at = ''
            """
        )
    else:
        conn.execute(
            "UPDATE leads SET updated_at = datetime('now') WHERE updated_at IS NULL OR updated_at = ''"
        )


def install_lead_file_triggers(conn: sqlite3.Connection) -> None:
    _install_touch_triggers(conn, "lead_files")


def backfill_updated_at_from_files(conn: sqlite3.Connection) -> None:
    cols = [row[1] for row in conn.execute("PRAGMA table_info(leads)")]
    if "updated_at" not in cols:
        return
    conn.execute(
        """
        UPDATE leads
        SET updated_at = (
            SELECT MAX(created_at) FROM lead_files WHERE lead_id = leads.id
        )
        WHERE EXISTS (
            SELECT 1 FROM lead_files
            WHERE lead_id = leads.id
              AND created_at IS NOT NULL
              AND created_at > COALESCE(leads.updated_at, '')
        )
        """
    )


def backup_sqlite(dest_path: str) -> None:
    """Согласованный снимок через online backup API: source.backup(dest). Файл назначения закрывается до возврата."""
    source = sqlite3.connect(str(DB_PATH), timeout=30)
    dest = sqlite3.connect(dest_path)
    try:
        source.backup(dest)
        dest.commit()
    finally:
        dest.close()
        source.close()


def normalize_since(value: str | None) -> str | None:
    """ISO-дата или datetime → 'YYYY-MM-DD HH:MM:SS'. Пустое значение — без фильтра."""
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip().replace("T", " ")
    if raw.endswith("Z"):
        raw = raw[:-1]
    raw = re.sub(r"[+-]\d{2}:?\d{2}$", "", raw)
    raw = re.sub(r"\.\d+$", "", raw)
    match = _SINCE_RE.match(raw)
    if not match:
        raise ValueError("bad since")
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour = int(match.group(4) or 0)
    minute = int(match.group(5) or 0)
    second = int(match.group(6) or 0)
    try:
        datetime(year, month, day, hour, minute, second)
    except ValueError:
        raise ValueError("bad since") from None
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"


def parse_include(value: str | None) -> frozenset[str]:
    """Пусто — все вложенные наборы. Иначе список из notes,objects,messages,files,payments."""
    if value is None or not str(value).strip():
        return frozenset(EXPORT_RELATIONS)
    parts = [part.strip() for part in str(value).split(",") if part.strip()]
    if not parts or any(part not in EXPORT_RELATIONS for part in parts):
        raise ValueError("bad include")
    return frozenset(parts)


def _stamp_ge(value, since: str) -> bool:
    stamp = _lead_stamp(value if isinstance(value, str) else ("" if value is None else str(value)))
    return bool(stamp) and stamp >= since


def _lead_changed(lead: dict, updated_at, bucket: dict, since: str) -> bool:
    if _stamp_ge(updated_at, since) or _stamp_ge(lead.get("created_at"), since):
        return True
    for name in ("notes", "messages", "files", "payments", "objects"):
        for item in bucket.get(name, []):
            if _stamp_ge(item.get("created_at"), since) or _stamp_ge(item.get("updated_at"), since):
                return True
    return False


def export_leads(since: str | None, include: frozenset[str]) -> list[dict]:
    """Все лиды одним проходом: один SELECT на таблицу, группировка в Python.

    since — уже нормализованный штамп. include — какие вложенные списки класть в ответ.
    Фильтр updated_since смотрит leads.updated_at и штампы вложенных строк, даже если набор не отдан.
    """
    relations = EXPORT_RELATIONS
    need = {name: since is not None or name in include for name in relations}
    from backend import files as lead_files

    with get_connection() as conn:
        leads = []
        stamps: dict[int, str | None] = {}
        grouped: dict[int, dict[str, list]] = {}
        rows = conn.execute(
            """
            SELECT id, name, phone, extra_phones, avito_link, max_link, tg_link, address,
                   object_type, budget, status, last_contact, comment, work_types, description,
                   deal_amount, communication_done, has_multiple_objects, avito_chat_id,
                   avito_new_chat, created_at, updated_at
            FROM leads ORDER BY id
            """
        ).fetchall()
        for row in rows:
            lead = _lead_row_to_dict(row)
            lead_id = lead["id"]
            stamps[lead_id] = lead.pop("updated_at", None)
            grouped[lead_id] = {name: [] for name in relations}
            leads.append(lead)

        if need["notes"]:
            for row in conn.execute(
                """
                SELECT id, lead_id, lead_object_id, text, created_at
                FROM notes ORDER BY lead_id, created_at DESC, id DESC
                """
            ):
                item = _row_to_dict(row)
                bucket = grouped.get(item["lead_id"])
                if bucket is not None:
                    bucket["notes"].append(item)
        if need["objects"]:
            for row in conn.execute(
                """
                SELECT id, lead_id, name, address, object_type, budget, work_types, description,
                       deal_amount, last_contact, sort_order
                FROM lead_objects ORDER BY lead_id, sort_order, id
                """
            ):
                item = _lead_object_row_to_dict(row)
                bucket = grouped.get(item["lead_id"])
                if bucket is not None:
                    bucket["objects"].append(item)
        if need["messages"]:
            for row in conn.execute(
                """
                SELECT id, lead_id, text, direction, source, created_at, avito_message_id
                FROM messages ORDER BY lead_id, created_at ASC, id ASC
                """
            ):
                item = _row_to_dict(row)
                bucket = grouped.get(item["lead_id"])
                if bucket is not None:
                    bucket["messages"].append(item)
        if need["payments"]:
            for row in conn.execute(
                """
                SELECT id, lead_id, object_id, paid_at, amount, note, source, external_id, created_at
                FROM payments ORDER BY lead_id, paid_at DESC, id DESC
                """
            ):
                item = _payment_row(row)
                bucket = grouped.get(item["lead_id"])
                if bucket is not None:
                    bucket["payments"].append(item)
        if need["files"]:
            try:
                file_rows = conn.execute(
                    "SELECT * FROM lead_files ORDER BY lead_id, created_at DESC, id DESC"
                ).fetchall()
            except sqlite3.OperationalError:
                file_rows = []
            for row in file_rows:
                item = lead_files._row(row)
                bucket = grouped.get(item["lead_id"])
                if bucket is not None:
                    bucket["files"].append(item)

    result = []
    for lead in leads:
        bucket = grouped[lead["id"]]
        if since is not None and not _lead_changed(lead, stamps.get(lead["id"]), bucket, since):
            continue
        for name in relations:
            if name in include:
                lead[name] = bucket[name]
        result.append(lead)
    return result
