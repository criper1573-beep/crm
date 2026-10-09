# Файлы лида: хранение на диске (вне веб-корня) + метаданные в SQLite (таблица lead_files)

import mimetypes
import os
import re
import uuid
from pathlib import Path

from backend import database

# Каталог хранения: data/files/<lead_id>/<uuid>. Отдаётся только через API.
FILES_DIR = Path(os.environ.get("CRM_FILES_DIR") or (Path(__file__).resolve().parent.parent / "data" / "files"))
MAX_FILE_SIZE = int(os.environ.get("CRM_MAX_FILE_MB", "50")) * 1024 * 1024
MAX_FILES_PER_REQUEST = 20
CHUNK = 1024 * 1024

# Типы, которые безопасно показывать в браузере inline. SVG/HTML — только скачиванием (XSS).
INLINE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/avif",
    "image/heic", "image/heif", "application/pdf",
}

_STORED_RE = re.compile(r"^[0-9a-f]{32}$")


class FileTooLarge(Exception):
    pass


def init_table() -> None:
    """Аддитивная миграция: только CREATE TABLE/INDEX IF NOT EXISTS."""
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


def save_stream(lead_id: int, fileobj) -> tuple[str, int]:
    """Пишет поток в data/files/<lead_id>/<uuid>. Возвращает (stored_name, size). Лимит MAX_FILE_SIZE."""
    d = lead_dir(lead_id)
    d.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex
    path = safe_path(lead_id, stored)
    tmp = path.with_name(stored + ".part")
    size = 0
    try:
        with open(tmp, "wb") as out:
            while True:
                chunk = fileobj.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise FileTooLarge()
                out.write(chunk)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    return stored, size


def _row(r) -> dict:
    d = dict(r)
    d.pop("stored_name", None)
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


def delete_file(lead_id: int, file_id: int) -> bool:
    raw = get_file_raw(lead_id, file_id)
    if not raw:
        return False
    with database.get_connection() as conn:
        conn.execute("DELETE FROM lead_files WHERE id = ? AND lead_id = ?", (file_id, lead_id))
        conn.commit()
    try:
        safe_path(lead_id, raw["stored_name"]).unlink()
    except (FileNotFoundError, ValueError):
        pass
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
