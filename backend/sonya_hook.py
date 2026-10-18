# Пересылка событий Авито ассистенту. Без SONYA_HOOK_URL или SONYA_HOOK_AUTH — no-op.

import logging
import os
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

# Аккаунт FLOW в Авито. Свои сообщения и системные события (author_id 0) не пересылаем.
OWN_AUTHOR_ID = "327789616"
SYSTEM_AUTHOR_ID = "0"

TIMEOUT_SECONDS = 5
_SEEN_MAX = 10000
# Москва без перехода на летнее время: постоянный UTC+3.
_MSK = timezone(timedelta(hours=3))

_seen_lock = threading.Lock()
_seen: OrderedDict[str, None] = OrderedDict()


def clear_seen_message_ids() -> None:
    """Сбросить in-memory дедуп. Нужен тестам и живёт только в памяти процесса."""
    with _seen_lock:
        _seen.clear()


def _remember(message_id: str) -> bool:
    """True, если этот message id ещё не пересылали."""
    with _seen_lock:
        if message_id in _seen:
            _seen.move_to_end(message_id)
            return False
        _seen[message_id] = None
        while len(_seen) > _SEEN_MAX:
            _seen.popitem(last=False)
        return True


def _hook_settings() -> tuple[str, str] | None:
    url = (os.environ.get("SONYA_HOOK_URL") or "").strip()
    auth = (os.environ.get("SONYA_HOOK_AUTH") or "").strip()
    if not url or not auth:
        return None
    return url, auth


def _event_value(event: dict) -> dict:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return {}
    value = payload.get("value")
    return value if isinstance(value, dict) else {}


def _author_key(value: dict) -> str:
    raw = value.get("author_id")
    if raw is None or isinstance(raw, bool):
        return ""
    return str(raw).strip()


def _message_id(value: dict) -> str:
    raw = value.get("id")
    if raw is None or isinstance(raw, bool):
        return ""
    return str(raw).strip()


def _chat_id(value: dict) -> str | None:
    raw = value.get("chat_id")
    if raw is None or isinstance(raw, bool):
        return None
    text = str(raw).strip()
    return text or None


def _message_text(value: dict) -> str:
    content = value.get("content")
    if not isinstance(content, dict):
        return ""
    text = content.get("text")
    if not isinstance(text, str):
        return ""
    return text.strip()


def _created_at_msk(raw: object) -> str | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        timestamp = int(raw)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=_MSK).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return None


def _should_forward(value: dict) -> bool:
    author = _author_key(value)
    if author in ("", SYSTEM_AUTHOR_ID, OWN_AUTHOR_ID):
        return False
    return bool(_message_id(value))


def build_forward_body(event: dict, lead_id: int | None, lead_created: bool) -> dict:
    """Тело для ассистента. webhook_event — исходный JSON Авито без изменений."""
    value = _event_value(event)
    body: dict = {
        "source": "avito",
        "webhook_event": event,
        "lead_id": lead_id,
        "lead_created": bool(lead_created),
        "chat_id": _chat_id(value),
        "author_id": value.get("author_id"),
        "message_type": value.get("type"),
        "created_at_msk": _created_at_msk(value.get("created")),
    }
    text = _message_text(value)
    if text:
        body["text"] = text
    return body


def _deliver(url: str, auth: str, payload: dict, message_id: str) -> None:
    """POST с таймаутом ~5 с и одним повтором на сеть или 5xx. Токен в лог не попадает."""
    headers = {"Authorization": auth, "Content-Type": "application/json"}
    reason: str | None = None
    try:
        for attempt in range(2):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                reason = exc.__class__.__name__
                if attempt == 0:
                    continue
                break
            status = response.status_code
            if status >= 500:
                reason = f"HTTP {status}"
                if attempt == 0:
                    continue
                break
            if status >= 400:
                reason = f"HTTP {status}"
                break
            return
    except Exception as exc:
        reason = exc.__class__.__name__
    if reason:
        logger.error("Sonya hook forward failed: %s message_id=%s", reason, message_id)


def forward_avito_event(event: dict, lead_id: int | None, lead_created: bool) -> None:
    """Переслать событие клиента. Чужие message id, свои и системные — молча пропускаются."""
    try:
        settings = _hook_settings()
        if settings is None or not isinstance(event, dict):
            return
        value = _event_value(event)
        if not _should_forward(value):
            return
        message_id = _message_id(value)
        if not _remember(message_id):
            return
        if lead_id is not None:
            lead_id = int(lead_id)
        url, auth = settings
        _deliver(url, auth, build_forward_body(event, lead_id, lead_created), message_id)
    except Exception as exc:
        logger.error("Sonya hook forward failed: %s", exc.__class__.__name__)
