# Файлы лида: хранение на диске (вне веб-корня) + метаданные в SQLite (таблица lead_files).
# Версии — таблица lead_file_versions, файлы в том же CRM_FILES_DIR (ночной rsync + sqlite backup).
# Имя с хвостом _vN / датой — это новая версия того же ключа, а не отдельная карточка.

import hashlib
import mimetypes
import os
import re
import sqlite3
import uuid
from pathlib import Path

from backend import database

# Каталог хранения: data/files/<lead_id>/<uuid>. Отдаётся только через API.
FILES_DIR = Path(os.environ.get("CRM_FILES_DIR") or (Path(__file__).resolve().parent.parent / "data" / "files"))
MAX_FILE_SIZE = int(os.environ.get("CRM_MAX_FILE_MB", "50")) * 1024 * 1024
MAX_FILES_PER_REQUEST = 20
CHUNK = 1024 * 1024

# Канонические категории. Сравнение без регистра, в базе хранится этот вид.
FILE_CATEGORIES = (
    "смета",
    "кп",
    "ведомость",
    "чертёж",
    "план",
    "материалы",
    "договор",
    "фото",
    "прочее",
)
_CATEGORY_CANON = {name.casefold(): name for name in FILE_CATEGORIES}

# Типы, которые безопасно показывать в браузере inline. SVG/HTML — только скачиванием (XSS).
INLINE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/avif",
    "image/heic", "image/heif", "application/pdf",
}

_STORED_RE = re.compile(r"^[0-9a-f]{32}$")
# Хвост перед расширением: _vN, _vN_YYYY-MM-DD, -vN, « vN» или одиночная дата _YYYY-MM-DD.
_VERSION_TAIL_RE = re.compile(
    r"(?:(?P<sep>[_\- ])v(?P<num>\d+)(?:_(?P<date>\d{4}-\d{2}-\d{2}))?|_(?P<onlydate>\d{4}-\d{2}-\d{2}))$",
    re.IGNORECASE,
)
# Префикс имени после номера лида. «исходники» и «план» — одна категория.
_NAME_CATEGORY_PREFIXES = (
    ("исходники", "план"),
    ("ведомость", "ведомость"),
    ("материалы", "материалы"),
    ("договор", "договор"),
    ("смета", "смета"),
    ("фото", "фото"),
    ("план", "план"),
    ("кп", "кп"),
)


class FileTooLarge(Exception):
    pass


class BadCategory(ValueError):
    pass


def normalize_category(value: str | None) -> str:
    """Белый список. Пустое и неизвестное значение — BadCategory."""
    canon = _CATEGORY_CANON.get((value or "").strip().casefold())
    if canon is None:
        raise BadCategory(value or "")
    return canon


def init_table() -> None:
    """Аддитивная миграция: CREATE TABLE/INDEX IF NOT EXISTS и новые nullable-колонки."""
    with database.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id),
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                size INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lead_files_lead ON lead_files(lead_id)")
        cols = [row[1] for row in conn.execute("PRAGMA table_info(lead_files)")]
        if "category" not in cols:
            conn.execute("ALTER TABLE lead_files ADD COLUMN category TEXT")
        if "version" not in cols:
            conn.execute("ALTER TABLE lead_files ADD COLUMN version INTEGER")
        if "sha256" not in cols:
            conn.execute("ALTER TABLE lead_files ADD COLUMN sha256 TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_file_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id),
                filename TEXT NOT NULL,
                version INTEGER NOT NULL,
                category TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                comment TEXT NOT NULL DEFAULT '',
                original_name TEXT NOT NULL DEFAULT '',
                sha256 TEXT NOT NULL,
                size INTEGER NOT NULL DEFAULT 0,
                stored_name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_file_versions_uniq
            ON lead_file_versions(lead_id, filename, version)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lead_file_versions_lead
            ON lead_file_versions(lead_id, filename, created_at)
            """
        )
        version_cols = [row[1] for row in conn.execute("PRAGMA table_info(lead_file_versions)")]
        if "original_name" not in version_cols:
            conn.execute(
                "ALTER TABLE lead_file_versions ADD COLUMN original_name TEXT NOT NULL DEFAULT ''"
            )
        database.install_lead_file_triggers(conn)
        database.backfill_updated_at_from_files(conn)
        conn.commit()


def sanitize_name(name: str | None) -> str:
    """Оставляет только базовое имя файла без путей и управляющих символов."""
    n = (name or "").replace("\\", "/").split("/")[-1]
    n = "".join(ch for ch in n if ch.isprintable() and ch not in '"<>|:*?\x00')
    n = n.strip().strip(".").strip()
    if not n:
        n = "file"
    if len(n) > 200:
        stem, ext = os.path.splitext(n)
        n = stem[: 200 - len(ext[:20])] + ext[:20]
    return n


def normalize_version_name(name: str | None) -> str:
    """Ключ версии: то же имя без хвоста _vN / -vN / « vN» / _vN_даты / _даты.

    Регистр и расширение не меняются. Пустой остаток не отрезается.
    """
    cleaned = sanitize_name(name)
    stem, ext = os.path.splitext(cleaned)
    match = _VERSION_TAIL_RE.search(stem)
    if not match:
        return cleaned
    new_stem = stem[: match.start()].rstrip()
    if not new_stem:
        return cleaned
    return new_stem + ext


def version_num_from_name(name: str | None) -> int:
    """Номер vN из хвоста исходного имени. Нет хвоста — 0."""
    stem, _ext = os.path.splitext(name or "")
    match = _VERSION_TAIL_RE.search(stem.strip())
    if not match or not match.group("num"):
        return 0
    return int(match.group("num"))


def category_from_name(name: str | None) -> str:
    """Категория по префиксу имени. Номер лида в начале (`423_`) не мешает. Иначе «прочее»."""
    stem = os.path.splitext(normalize_version_name(name))[0].casefold()
    tail = re.sub(r"^\d+[_\-\s]+", "", stem).lstrip("_- ")
    for prefix, category in _NAME_CATEGORY_PREFIXES:
        if tail.startswith(prefix) or stem.startswith(prefix):
            return category
    return "прочее"


def guess_mime(name: str, declared: str | None) -> str:
    mt, _ = mimetypes.guess_type(name)
    if mt:
        return mt
    if declared and re.match(r"^[\w.+-]+/[\w.+-]+$", declared):
        return declared
    return "application/octet-stream"


def lead_dir(lead_id: int) -> Path:
    return FILES_DIR / str(int(lead_id))


def safe_path(lead_id: int, stored_name: str) -> Path:
    """Путь к файлу на диске; гарантирует, что он внутри FILES_DIR."""
    if not _STORED_RE.match(stored_name or ""):
        raise ValueError("bad stored name")
    base = FILES_DIR.resolve()
    p = (lead_dir(lead_id) / stored_name).resolve()
    if base not in p.parents:
        raise ValueError("path outside storage")
    return p


def _write_stream(lead_id: int, fileobj) -> tuple[str, int, str]:
    """Пишет поток в CRM_FILES_DIR/<lead_id>/<uuid>. Возвращает (stored_name, size, sha256)."""
    d = lead_dir(lead_id)
    d.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex
    path = safe_path(lead_id, stored)
    tmp = path.with_name(stored + ".part")
    size = 0
    hasher = hashlib.sha256()
    try:
        with open(tmp, "wb") as out:
            while True:
                chunk = fileobj.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise FileTooLarge()
                hasher.update(chunk)
                out.write(chunk)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    return stored, size, hasher.hexdigest()


def save_stream(lead_id: int, fileobj) -> tuple[str, int]:
    """Пишет поток в data/files/<lead_id>/<uuid>. Возвращает (stored_name, size). Лимит MAX_FILE_SIZE."""
    stored, size, _digest = _write_stream(lead_id, fileobj)
    return stored, size


def save_stream_hashed(lead_id: int, fileobj) -> tuple[str, int, str]:
    """Тот же каталог, что у карточки лида, плюс sha256 содержимого."""
    return _write_stream(lead_id, fileobj)


def _row(r) -> dict:
    d = dict(r)
    d.pop("stored_name", None)
    # Колонки версий не отдаём старым эндпоинтам: карточка и экспорт остаются прежними.
    d.pop("category", None)
    d.pop("version", None)
    d.pop("sha256", None)
    d["url"] = f"/api/leads/{d['lead_id']}/files/{d['id']}"
    d["is_image"] = d["mime_type"].startswith("image/") and d["mime_type"] in INLINE_TYPES
    return d


def insert_file(lead_id: int, original_name: str, stored_name: str, mime: str, size: int) -> dict:
    with database.get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO lead_files (lead_id, original_name, stored_name, mime_type, size) VALUES (?, ?, ?, ?, ?)",
            (lead_id, original_name, stored_name, mime, size),
        )
        conn.commit()
        r = conn.execute("SELECT * FROM lead_files WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row(r)


def list_files(lead_id: int) -> list[dict]:
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM lead_files WHERE lead_id = ? ORDER BY created_at DESC, id DESC", (lead_id,)
        ).fetchall()
        return [_row(r) for r in rows]


def get_file_raw(lead_id: int, file_id: int) -> dict | None:
    with database.get_connection() as conn:
        r = conn.execute(
            "SELECT * FROM lead_files WHERE id = ? AND lead_id = ?", (file_id, lead_id)
        ).fetchone()
        return dict(r) if r else None


def _storage_in_use(conn: sqlite3.Connection, lead_id: int, stored_name: str) -> bool:
    if conn.execute(
        "SELECT 1 FROM lead_files WHERE lead_id = ? AND stored_name = ? LIMIT 1",
        (lead_id, stored_name),
    ).fetchone():
        return True
    return conn.execute(
        "SELECT 1 FROM lead_file_versions WHERE lead_id = ? AND stored_name = ? LIMIT 1",
        (lead_id, stored_name),
    ).fetchone() is not None


def _unlink_if_unused(conn: sqlite3.Connection, lead_id: int, stored_name: str | None) -> None:
    if not stored_name or _storage_in_use(conn, lead_id, stored_name):
        return
    remove_stored(lead_id, stored_name)


def delete_file(lead_id: int, file_id: int) -> bool:
    raw = get_file_raw(lead_id, file_id)
    if not raw:
        return False
    stored = raw["stored_name"]
    with database.get_connection() as conn:
        conn.execute("DELETE FROM lead_files WHERE id = ? AND lead_id = ?", (file_id, lead_id))
        conn.commit()
        # Версия могла ссылаться на тот же файл: историю и бэкап не дырявим.
        if not _storage_in_use(conn, lead_id, stored):
            remove_stored(lead_id, stored)
    return True


def remove_stored(lead_id: int, stored_name: str) -> None:
    try:
        safe_path(lead_id, stored_name).unlink()
    except (FileNotFoundError, ValueError):
        pass


def counts_by_lead() -> dict[int, int]:
    with database.get_connection() as conn:
        rows = conn.execute("SELECT lead_id, COUNT(*) AS c FROM lead_files GROUP BY lead_id").fetchall()
        return {r["lead_id"]: r["c"] for r in rows}


def _plain(value: str | None) -> str:
    return (value or "").replace("\x00", "").strip()


def _version_public(row) -> dict:
    d = dict(row)
    d.pop("stored_name", None)
    d["url"] = f"/api/leads/{d['lead_id']}/files/versions/{d['id']}/raw"
    return d


def _upsert_current(conn: sqlite3.Connection, lead_id: int, filename: str, stored_name: str, mime: str, size: int, category: str, version: int, sha256: str) -> str | None:
    """Обновляет последнюю карточку с этим именем или создаёт её. Возвращает прежний stored_name."""
    current = conn.execute(
        """
        SELECT id, stored_name FROM lead_files
        WHERE lead_id = ? AND original_name = ?
        ORDER BY id DESC LIMIT 1
        """,
        (lead_id, filename),
    ).fetchone()
    if current:
        previous = current["stored_name"] if current["stored_name"] != stored_name else None
        conn.execute(
            """
            UPDATE lead_files
            SET stored_name = ?, mime_type = ?, size = ?, category = ?, version = ?, sha256 = ?,
                created_at = datetime('now')
            WHERE id = ?
            """,
            (stored_name, mime, size, category, version, sha256, current["id"]),
        )
        return previous
    conn.execute(
        """
        INSERT INTO lead_files
            (lead_id, original_name, stored_name, mime_type, size, category, version, sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (lead_id, filename, stored_name, mime, size, category, version, sha256),
    )
    return None


def register_version(
    lead_id: int,
    filename: str,
    category: str,
    author: str,
    comment: str,
    stored_name: str,
    size: int,
    sha256: str,
    mime: str,
    original_name: str = "",
) -> dict:
    """Пишет версию n+1 и карточку lead_files. Тот же sha256, что у последней версии имени, — пропуск.

    filename — уже нормализованный ключ или сырое имя: хвост версии срезается здесь.
    Исходное имя остаётся в original_name и, если комментарий пуст, в comment.
    В заметки лида ничего не пишет.
    """
    author = _plain(author)
    source_name = _plain(original_name) or _plain(filename) or filename
    filename = normalize_version_name(filename)
    comment = _plain(comment)
    if not comment and source_name != filename:
        comment = source_name
    old_stored: str | None = None
    skipped: int | None = None
    kept_stored: str | None = None
    public: dict | None = None
    committed = False
    try:
        with database.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            latest = conn.execute(
                """
                SELECT version, sha256, stored_name FROM lead_file_versions
                WHERE lead_id = ? AND filename = ?
                ORDER BY version DESC, id DESC LIMIT 1
                """,
                (lead_id, filename),
            ).fetchone()
            if latest and latest["sha256"] == sha256:
                skipped = int(latest["version"])
                kept_stored = latest["stored_name"]
            else:
                version = int(latest["version"]) + 1 if latest else 1
                cur = conn.execute(
                    """
                    INSERT INTO lead_file_versions
                        (lead_id, filename, version, category, author, comment, original_name,
                         sha256, size, stored_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lead_id,
                        filename,
                        version,
                        category,
                        author,
                        comment,
                        source_name,
                        sha256,
                        size,
                        stored_name,
                    ),
                )
                old_stored = _upsert_current(
                    conn, lead_id, filename, stored_name, mime, size, category, version, sha256
                )
                conn.commit()
                committed = True
                row = conn.execute(
                    "SELECT * FROM lead_file_versions WHERE id = ?", (cur.lastrowid,)
                ).fetchone()
                public = _version_public(row)
                public["skipped"] = False
    except Exception:
        if not committed:
            remove_stored(lead_id, stored_name)
        raise
    if skipped is not None:
        if kept_stored != stored_name:
            remove_stored(lead_id, stored_name)
        return {"skipped": True, "version": skipped}
    if old_stored:
        with database.get_connection() as conn:
            _unlink_if_unused(conn, lead_id, old_stored)
    return public


def list_versions(lead_id: int, since: str | None, filename: str | None) -> list[dict]:
    """История: новые сверху. since — уже нормализованный штамп YYYY-MM-DD HH:MM:SS.

    Фильтр по имени принимает и ключ, и имя с хвостом версии: оба ищут одну цепочку.
    Строка, записанная ещё под старым именем, по точному совпадению тоже находится.
    """
    exact = (filename or "").strip() or None
    alternate = None
    if exact:
        normalized = normalize_version_name(exact)
        if normalized != exact:
            alternate = normalized
    with database.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM lead_file_versions
            WHERE lead_id = ?
              AND (
                    ? IS NULL
                    OR filename = ?
                    OR (? IS NOT NULL AND filename = ?)
                  )
              AND (? IS NULL OR created_at >= ?)
            ORDER BY created_at DESC, id DESC
            """,
            (lead_id, exact, exact, alternate, alternate, since, since),
        ).fetchall()
        return [_version_public(row) for row in rows]


def card_for_filename(lead_id: int, filename: str) -> dict | None:
    """Публичная карточка по ключу версии. Если карточку сняли, а версия жива — возвращает строку."""
    key = normalize_version_name(filename)
    with database.get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM lead_files
            WHERE lead_id = ? AND original_name = ?
            ORDER BY id DESC LIMIT 1
            """,
            (lead_id, key),
        ).fetchone()
        if row:
            return _row(row)
        latest = conn.execute(
            """
            SELECT * FROM lead_file_versions
            WHERE lead_id = ? AND filename = ?
            ORDER BY version DESC, id DESC LIMIT 1
            """,
            (lead_id, key),
        ).fetchone()
        if not latest:
            return None
        _upsert_current(
            conn,
            lead_id,
            key,
            latest["stored_name"],
            guess_mime(key, None),
            int(latest["size"]),
            latest["category"],
            int(latest["version"]),
            latest["sha256"],
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT * FROM lead_files
            WHERE lead_id = ? AND original_name = ?
            ORDER BY id DESC LIMIT 1
            """,
            (lead_id, key),
        ).fetchone()
        return _row(row) if row else None


def get_version_raw(lead_id: int, version_id: int) -> dict | None:
    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM lead_file_versions WHERE id = ? AND lead_id = ?",
            (version_id, lead_id),
        ).fetchone()
        return dict(row) if row else None


def delete_version(lead_id: int, version_id: int) -> bool:
    """Удаляет версию. Если это файл карточки — откатывает lead_files на предыдущую или убирает строку."""
    with database.get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM lead_file_versions WHERE id = ? AND lead_id = ?",
            (version_id, lead_id),
        ).fetchone()
        if not row:
            return False
        filename = row["filename"]
        stored = row["stored_name"]
        current = conn.execute(
            """
            SELECT * FROM lead_files
            WHERE lead_id = ? AND original_name = ?
            ORDER BY id DESC LIMIT 1
            """,
            (lead_id, filename),
        ).fetchone()
        conn.execute(
            "DELETE FROM lead_file_versions WHERE id = ? AND lead_id = ?",
            (version_id, lead_id),
        )
        if current and current["stored_name"] == stored:
            prev = conn.execute(
                """
                SELECT * FROM lead_file_versions
                WHERE lead_id = ? AND filename = ?
                ORDER BY version DESC, id DESC LIMIT 1
                """,
                (lead_id, filename),
            ).fetchone()
            if prev:
                conn.execute(
                    """
                    UPDATE lead_files
                    SET stored_name = ?, mime_type = ?, size = ?, category = ?, version = ?, sha256 = ?,
                        created_at = ?
                    WHERE id = ?
                    """,
                    (
                        prev["stored_name"],
                        guess_mime(filename, None),
                        prev["size"],
                        prev["category"],
                        prev["version"],
                        prev["sha256"],
                        prev["created_at"],
                        current["id"],
                    ),
                )
            else:
                conn.execute("DELETE FROM lead_files WHERE id = ?", (current["id"],))
        conn.commit()
        _unlink_if_unused(conn, lead_id, stored)
    return True


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _cell(row, name: str, default=""):
    if name not in row.keys():
        return default
    value = row[name]
    return default if value is None else value


def _sha256_file(lead_id: int, stored_name: str) -> str:
    path = safe_path(lead_id, stored_name)
    if not path.is_file():
        return ""
    hasher = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _prefer_original(current: str, incoming: str) -> str:
    current_num = version_num_from_name(current)
    incoming_num = version_num_from_name(incoming)
    if incoming_num and not current_num:
        return incoming
    if current_num and not incoming_num:
        return current or incoming
    if incoming_num and len(incoming or "") > len(current or ""):
        return incoming
    return current or incoming


def _earlier_stamp(current: str, incoming: str) -> str:
    if not current:
        return incoming or ""
    if not incoming:
        return current
    return current if current <= incoming else incoming


def _blank_item() -> dict:
    return {
        "original_name": "",
        "stored_name": "",
        "sha256": "",
        "size": 0,
        "mime": "",
        "created_at": "",
        "author": "",
        "comment": "",
        "file_id": None,
        "version_id": None,
        "file_ids": [],
        "version_ids": [],
        "version": 0,
    }


def _item_from_file(row) -> dict:
    item = _blank_item()
    item.update(
        {
            "original_name": _cell(row, "original_name"),
            "stored_name": _cell(row, "stored_name"),
            "sha256": _cell(row, "sha256"),
            "size": int(_cell(row, "size", 0) or 0),
            "mime": _cell(row, "mime_type"),
            "created_at": _cell(row, "created_at"),
            "file_id": int(row["id"]),
            "file_ids": [int(row["id"])],
        }
    )
    return item


def _item_from_version(row) -> dict:
    original = _cell(row, "original_name") or _cell(row, "filename")
    item = _blank_item()
    item.update(
        {
            "original_name": original,
            "stored_name": _cell(row, "stored_name"),
            "sha256": _cell(row, "sha256"),
            "size": int(_cell(row, "size", 0) or 0),
            "created_at": _cell(row, "created_at"),
            "author": _cell(row, "author"),
            "comment": _cell(row, "comment"),
            "version_id": int(row["id"]),
            "version_ids": [int(row["id"])],
        }
    )
    return item


def _merge_item(prev: dict, incoming: dict) -> None:
    for version_id in incoming.get("version_ids") or []:
        if version_id not in prev["version_ids"]:
            prev["version_ids"].append(version_id)
    if incoming["version_id"] and not prev["version_id"]:
        prev["version_id"] = incoming["version_id"]
    if incoming["author"] and (incoming["version_id"] or not prev["author"]):
        prev["author"] = incoming["author"]
    for file_id in incoming.get("file_ids") or []:
        if file_id not in prev["file_ids"]:
            prev["file_ids"].append(file_id)
    if incoming["file_id"] and not prev["file_id"]:
        prev["file_id"] = incoming["file_id"]
    if incoming["mime"] and not prev["mime"]:
        prev["mime"] = incoming["mime"]
    if incoming["comment"] and not prev["comment"]:
        prev["comment"] = incoming["comment"]
    if not prev["sha256"]:
        prev["sha256"] = incoming["sha256"]
    if not prev["size"]:
        prev["size"] = incoming["size"]
    prev["original_name"] = _prefer_original(prev["original_name"], incoming["original_name"])
    prev["created_at"] = _earlier_stamp(prev["created_at"], incoming["created_at"])


def _fill_hash(lead_id: int, item: dict) -> None:
    if item["sha256"]:
        return
    try:
        item["sha256"] = _sha256_file(lead_id, item["stored_name"])
    except (OSError, ValueError):
        item["sha256"] = ""
    if not item["sha256"]:
        # Пустой хеш не схлопываем с другими: у каждого такого файла свой ключ.
        item["sha256"] = "missing:" + (item["stored_name"] or str(item["file_id"] or item["version_id"]))


def _group_items(files, versions) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    index: dict[tuple[str, str], dict] = {}

    def add(key: str, item: dict) -> None:
        bucket = groups.setdefault(key, [])
        slot = index.get((key, item["stored_name"]))
        if slot is None:
            bucket.append(item)
            index[(key, item["stored_name"])] = item
            return
        _merge_item(slot, item)

    for row in files:
        add(normalize_version_name(_cell(row, "original_name")), _item_from_file(row))
    for row in versions:
        add(normalize_version_name(_cell(row, "filename")), _item_from_version(row))
    return groups


def _ordered_chain(lead_id: int, items: list[dict]) -> tuple[list[dict], list[dict]]:
    for item in items:
        _fill_hash(lead_id, item)
    items.sort(
        key=lambda item: (
            version_num_from_name(item["original_name"]),
            item["created_at"] or "",
            item["version_id"] or 0,
            item["file_id"] or 0,
        )
    )
    kept: list[dict] = []
    collapsed: list[dict] = []
    seen_hash: set[str] = set()
    seen_stored: set[str] = set()
    for item in items:
        digest = item["sha256"]
        if item["stored_name"] in seen_stored or (digest and digest in seen_hash):
            collapsed.append(item)
            continue
        seen_stored.add(item["stored_name"])
        if digest:
            seen_hash.add(digest)
        kept.append(item)
    for number, item in enumerate(kept, start=1):
        item["version"] = number
    return kept, collapsed


def _chain_is_current(conn: sqlite3.Connection, lead_id: int, key: str, kept: list[dict], category: str) -> bool:
    if not kept:
        return True
    latest = kept[-1]
    cards = [
        row
        for row in conn.execute("SELECT * FROM lead_files WHERE lead_id = ?", (lead_id,)).fetchall()
        if normalize_version_name(_cell(row, "original_name")) == key
    ]
    # Карточка нужна, когда в группе есть строки lead_files. История без карточки её не возрождает.
    had_files = bool(cards) or any(item["file_id"] for item in kept)
    if had_files:
        if len(cards) != 1:
            return False
        card = cards[0]
        if card["original_name"] != key:
            return False
        if card["stored_name"] != latest["stored_name"]:
            return False
        if int(card["version"] or 0) != len(kept):
            return False
        if (_cell(card, "sha256")) != latest["sha256"]:
            return False
        if (_cell(card, "category")) != category:
            return False
        if int(card["size"] or 0) != int(latest["size"] or 0):
            return False
    versions = [
        row
        for row in conn.execute(
            "SELECT * FROM lead_file_versions WHERE lead_id = ?", (lead_id,)
        ).fetchall()
        if normalize_version_name(_cell(row, "filename")) == key
    ]
    if len(versions) != len(kept):
        return False
    versions.sort(key=lambda row: (int(row["version"]), int(row["id"])))
    for index, (row, item) in enumerate(zip(versions, kept), start=1):
        if row["filename"] != key or int(row["version"]) != index:
            return False
        if row["stored_name"] != item["stored_name"] or _cell(row, "sha256") != item["sha256"]:
            return False
        if _cell(row, "original_name") != (item["original_name"] or key):
            return False
        if _cell(row, "category") != category:
            return False
        if int(row["size"] or 0) != int(item["size"] or 0):
            return False
    return True


def _plan_group(lead_id: int, key: str, items: list[dict], conn: sqlite3.Connection) -> dict:
    kept, collapsed = _ordered_chain(lead_id, items)
    category = category_from_name(key)
    file_ids = []
    for item in kept + collapsed:
        for file_id in item.get("file_ids") or []:
            if file_id not in file_ids:
                file_ids.append(file_id)
    latest = kept[-1]
    return {
        "lead_id": lead_id,
        "filename": key,
        "category": category,
        "changed": not _chain_is_current(conn, lead_id, key, kept, category),
        "kept": kept,
        "collapsed": collapsed,
        "file_ids": file_ids,
        "card": {
            "version": len(kept),
            "sha256": latest["sha256"],
            "stored_name": latest["stored_name"],
            "category": category,
            "size": latest["size"],
            "original_name": key,
        }
        if file_ids
        else None,
    }


def _ensure_original_name_column() -> None:
    """Только колонка исходного имени. Чужие строки и updated_at не трогает."""
    with database.get_connection() as conn:
        cols = _column_names(conn, "lead_file_versions")
        if cols and "original_name" not in cols:
            conn.execute(
                "ALTER TABLE lead_file_versions ADD COLUMN original_name TEXT NOT NULL DEFAULT ''"
            )
            conn.commit()


def _apply_group(conn: sqlite3.Connection, lead_id: int, plan: dict) -> None:
    key = plan["filename"]
    category = plan["category"]
    kept = plan["kept"]
    collapsed = plan["collapsed"]
    if not kept:
        return
    involved: list[int] = []
    for item in kept + collapsed:
        for version_id in item.get("version_ids") or []:
            if version_id not in involved:
                involved.append(int(version_id))
    for version_id in involved:
        conn.execute(
            "UPDATE lead_file_versions SET version = ? WHERE id = ?",
            (-int(version_id), int(version_id)),
        )
    drop_ids = []
    for item in collapsed:
        drop_ids.extend(int(version_id) for version_id in (item.get("version_ids") or []))
    for item in kept:
        primary = int(item["version_id"]) if item["version_id"] else None
        for version_id in item.get("version_ids") or []:
            if primary is not None and int(version_id) != primary:
                drop_ids.append(int(version_id))
    for version_id in drop_ids:
        conn.execute("DELETE FROM lead_file_versions WHERE id = ?", (int(version_id),))
    for item in kept:
        original = item["original_name"] or key
        comment = _plain(item["comment"])
        if not comment and original != key:
            comment = original
        author = item["author"] or "consolidate"
        if item["version_id"]:
            conn.execute(
                """
                UPDATE lead_file_versions
                SET filename = ?, version = ?, category = ?, author = ?, comment = ?,
                    original_name = ?, sha256 = ?, size = ?, stored_name = ?, created_at = ?
                WHERE id = ?
                """,
                (
                    key,
                    int(item["version"]),
                    category,
                    author,
                    comment,
                    original,
                    item["sha256"],
                    int(item["size"] or 0),
                    item["stored_name"],
                    item["created_at"] or None,
                    int(item["version_id"]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO lead_file_versions
                    (lead_id, filename, version, category, author, comment, original_name,
                     sha256, size, stored_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    key,
                    int(item["version"]),
                    category,
                    author,
                    comment,
                    original,
                    item["sha256"],
                    int(item["size"] or 0),
                    item["stored_name"],
                    item["created_at"] or None,
                ),
            )
    file_ids = plan["file_ids"]
    if not file_ids:
        return
    latest = kept[-1]
    keep_id = None
    for item in reversed(kept):
        if item["file_id"] and item["stored_name"] == latest["stored_name"]:
            keep_id = int(item["file_id"])
            break
    if keep_id is None:
        keep_id = int(file_ids[0])
    mime = latest.get("mime") or guess_mime(key, None)
    conn.execute(
        """
        UPDATE lead_files
        SET original_name = ?, stored_name = ?, mime_type = ?, size = ?, category = ?,
            version = ?, sha256 = ?, created_at = ?
        WHERE id = ?
        """,
        (
            key,
            latest["stored_name"],
            mime,
            int(latest["size"] or 0),
            category,
            len(kept),
            latest["sha256"],
            latest["created_at"] or None,
            keep_id,
        ),
    )
    for file_id in file_ids:
        if int(file_id) != keep_id:
            conn.execute("DELETE FROM lead_files WHERE id = ?", (int(file_id),))


def _lead_ids(conn: sqlite3.Connection, lead_id: int | None, all_leads: bool) -> list[int]:
    if lead_id is not None:
        return [int(lead_id)]
    if not all_leads:
        raise ValueError("lead_id or all_leads is required")
    rows = conn.execute(
        """
        SELECT lead_id FROM (
            SELECT lead_id FROM lead_files
            UNION
            SELECT lead_id FROM lead_file_versions
        )
        ORDER BY lead_id
        """
    ).fetchall()
    return [int(row[0]) for row in rows]


def plan_version_consolidation(lead_id: int | None = None, *, all_leads: bool = False) -> list[dict]:
    """План схлопывания без записи. Файлы на диске только читаются, чтобы посчитать sha256."""
    with database.get_connection() as conn:
        ids = _lead_ids(conn, lead_id, all_leads)
        plans: list[dict] = []
        for current in ids:
            files = conn.execute("SELECT * FROM lead_files WHERE lead_id = ?", (current,)).fetchall()
            versions = conn.execute(
                "SELECT * FROM lead_file_versions WHERE lead_id = ?", (current,)
            ).fetchall()
            for key, items in _group_items(files, versions).items():
                plans.append(_plan_group(current, key, items, conn))
        return plans


def consolidate_versions(
    lead_id: int | None = None, *, all_leads: bool = False, dry_run: bool = False
) -> list[dict]:
    """Группирует карточки лида по нормализованному имени и собирает из них историю v1..vk.

    Байты не копирует и не удаляет: версии ссылаются на уже лежащие stored_name.
    Одинаковый sha256 внутри группы остаётся одной версией. В lead_files — одна
    строка на ключ, с полями последней версии. dry_run только возвращает план.
    """
    if not dry_run:
        _ensure_original_name_column()
    plans = plan_version_consolidation(lead_id, all_leads=all_leads)
    if dry_run:
        return plans
    pending = [plan for plan in plans if plan["changed"]]
    by_lead: dict[int, list[dict]] = {}
    for plan in pending:
        by_lead.setdefault(int(plan["lead_id"]), []).append(plan)
    for current, groups in by_lead.items():
        with database.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for plan in groups:
                _apply_group(conn, current, plan)
            conn.commit()
    return plans


def format_consolidation_plan(plans: list[dict], *, dry_run: bool) -> str:
    """Текст плана для скрипта: что сольётся в какую цепочку."""
    lines: list[str] = []
    if dry_run:
        lines.append("dry-run: база и файлы не изменяются")
    changed = [plan for plan in plans if plan["changed"]]
    if not plans:
        lines.append("нечего схлопывать")
        return "\n".join(lines)
    lines.append(f"групп {len(plans)}, к изменению {len(changed)}")
    current_lead = None
    for plan in changed:
        if plan["lead_id"] != current_lead:
            current_lead = plan["lead_id"]
            lines.append(f"лид {current_lead}")
        lines.append(
            f"  {plan['filename']}  категория {plan['category']}"
            f"  версии {len(plan['kept'])}  схлопнуто {len(plan['collapsed'])}"
        )
        for item in plan["kept"]:
            digest = (item["sha256"] or "")[:12]
            lines.append(
                f"    v{item['version']}  {item['original_name']}  {digest}  {item['stored_name']}"
            )
        for item in plan["collapsed"]:
            digest = (item["sha256"] or "")[:12]
            lines.append(
                f"    дубль  {item['original_name']}  {digest}  {item['stored_name']}"
            )
        if plan["card"]:
            lines.append(
                f"    карточка version={plan['card']['version']}"
                f" sha={(plan['card']['sha256'] or '')[:12]}"
                f" category={plan['card']['category']}"
            )
    if not changed:
        lines.append("уже собрано, правок нет")
    return "\n".join(lines)
