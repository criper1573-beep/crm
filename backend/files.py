# Файлы лида: хранение на диске (вне веб-корня) + метаданные в SQLite (таблица lead_files).
# Версии ботов — таблица lead_file_versions, файлы в том же CRM_FILES_DIR (ночной rsync + sqlite backup).

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
) -> dict:
    """Пишет версию n+1 и карточку lead_files. Тот же sha256, что у последней версии имени, — пропуск.

    В заметки лида ничего не пишет.
    """
    author = _plain(author)
    comment = _plain(comment)
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
                        (lead_id, filename, version, category, author, comment, sha256, size, stored_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (lead_id, filename, version, category, author, comment, sha256, size, stored_name),
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
    """История: новые сверху. since — уже нормализованный штамп YYYY-MM-DD HH:MM:SS."""
    name = (filename or "").strip() or None
    with database.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM lead_file_versions
            WHERE lead_id = ?
              AND (? IS NULL OR filename = ?)
              AND (? IS NULL OR created_at >= ?)
            ORDER BY created_at DESC, id DESC
            """,
            (lead_id, name, name, since, since),
        ).fetchall()
        return [_version_public(row) for row in rows]


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
