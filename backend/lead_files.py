# Файлы документов лида: каталог на диске и безопасные имена.
# На диске только uuid (и безопасное расширение). Исходное имя живёт в SQLite.

import logging
import mimetypes
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger("backend.lead_files")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024
_STORED_NAME_RE = re.compile(r"^[0-9a-f]{32}(?:\.[A-Za-z0-9]{1,10})?$")
_MEDIA_RE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$")

# Открываем в браузере только эти типы, и только если расширение с ними совпадает.
_INLINE_EXT = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/gif": {".gif"},
    "image/webp": {".webp"},
}
_ACTIVE_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "image/svg+xml",
    "text/javascript",
    "application/javascript",
    "application/x-javascript",
}


class FileTooLarge(Exception):
    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"File exceeds size limit of {limit} bytes")


class InvalidStoredName(Exception):
    pass


def files_dir() -> Path:
    """Каталог хранения. CRM_FILES_DIR или data/files рядом с базой."""
    raw = os.environ.get("CRM_FILES_DIR", "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
    else:
        path = _PROJECT_ROOT / "data" / "files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def max_upload_bytes() -> int:
    raw = os.environ.get("CRM_MAX_UPLOAD_BYTES", "").strip()
    if not raw:
        return _DEFAULT_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_BYTES
    if value <= 0:
        return _DEFAULT_MAX_BYTES
    return value


def clean_original_name(name: str | None) -> str:
    raw = (name or "").replace("\x00", "").strip()
    if not raw:
        return "file"
    if len(raw) > 500:
        return raw[:500]
    return raw


def safe_suffix(original_name: str) -> str:
    """Расширение берётся только из последнего сегмента имени, не из пути."""
    base = Path(original_name).name
    suffix = Path(base).suffix.lower()
    ext = suffix[1:] if suffix.startswith(".") else ""
    if ext.isascii() and ext.isalnum() and 1 <= len(ext) <= 10:
        return "." + ext
    return ""


def safe_media_type(value: str | None, original_name: str) -> str:
    raw = (value or "").split(";")[0].strip().lower()
    if _MEDIA_RE.fullmatch(raw):
        return raw
    guessed, _ = mimetypes.guess_type(Path(original_name).name)
    if guessed and _MEDIA_RE.fullmatch(guessed):
        return guessed
    return "application/octet-stream"


def resolve_stored_path(stored_name: str) -> Path:
    """Путь внутри каталога хранения. Имена с .., слешами и не-uuid отклоняются."""
    if not stored_name or not _STORED_NAME_RE.fullmatch(stored_name):
        raise InvalidStoredName(stored_name)
    root = files_dir().resolve()
    path = (root / stored_name).resolve()
    if path.parent != root:
        raise InvalidStoredName(stored_name)
    return path


def save_upload(source, original_name: str) -> tuple[str, int]:
    """Пишет поток на диск под uuid-именем. При превышении лимита файл удаляется."""
    limit = max_upload_bytes()
    stored_name = uuid.uuid4().hex + safe_suffix(original_name)
    path = resolve_stored_path(stored_name)
    size = 0
    try:
        with path.open("wb") as out:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                if size + len(chunk) > limit:
                    raise FileTooLarge(limit)
                out.write(chunk)
                size += len(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return stored_name, size


def remove_stored_files(stored_names: list[str]) -> None:
    for name in stored_names:
        try:
            path = resolve_stored_path(name)
        except InvalidStoredName:
            logger.warning("skip unsafe stored name: %s", name)
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("failed to delete lead file %s", path)


def content_disposition(original_name: str, *, attachment: bool) -> str:
    """RFC 5987: ASCII fallback и filename* для кириллицы. В заголовок не попадают CR/LF."""
    name = (original_name or "file").replace("\r", "").replace("\n", "").replace("\x00", "")
    if not name.strip():
        name = "file"
    kind = "attachment" if attachment else "inline"
    fallback_chars = []
    for ch in name:
        if 32 <= ord(ch) < 127 and ch not in {'"', "\\"}:
            fallback_chars.append(ch)
        else:
            fallback_chars.append("_")
    fallback = "".join(fallback_chars).strip(" .") or "file"
    if len(fallback) > 180:
        fallback = fallback[:180]
    encoded = quote(name, safe="")
    return f"{kind}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def serve_disposition(content_type: str, original_name: str, *, force_download: bool) -> tuple[str, bool]:
    """Возвращает (media_type, attachment). HTML/SVG не отдаются как активный контент того же сайта."""
    media = safe_media_type(content_type, original_name)
    ext = safe_suffix(original_name)
    can_inline = media in _INLINE_EXT and ext in _INLINE_EXT[media]
    if can_inline and not force_download:
        return media, False
    if media in _ACTIVE_TYPES or media.startswith("text/html"):
        return "application/octet-stream", True
    return media or "application/octet-stream", True
