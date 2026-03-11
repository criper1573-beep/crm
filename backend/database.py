# SQLite logic

import json
import sqlite3
from pathlib import Path

from backend.models import Lead, LeadObject, LeadObjectCreate, NoteCreate, MessageCreate, MessageBulkItem

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
    return leads_list


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
