# GRS AI API client for CRM (config from project .env only)

import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env from CRM project root
_CRM_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_CRM_ROOT / ".env")

DEFAULT_MODEL = "gpt-4o-mini"
# Таймаут запроса к GRS AI (сек). Через .env: GRS_AI_TIMEOUT=180
TIMEOUT = int(os.getenv("GRS_AI_TIMEOUT", "180"))


def _log(msg):
    log_path = os.path.join(os.path.dirname(__file__), "..", "data", "grs_debug.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def _get_config():
    api_key = os.getenv("GRS_AI_API_KEY")
    base_url = (os.getenv("GRS_AI_API_URL") or "https://grsaiapi.com").rstrip("/")
    return api_key, base_url


def chat_completion(messages: list[dict], model: str | None = None, max_tokens: int | None = None) -> str:
    """
    Send messages to GRS AI Chat Completions API, return assistant text.
    messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    api_key, base_url = _get_config()
    if not api_key:
        raise ValueError("GRS_AI_API_KEY is not set in .env")

    url = f"{base_url}/v1/chat/completions"
    model = model or DEFAULT_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens if max_tokens is not None else 800,
        "stream": False,
    }

    logger.info(f"GRS AI request to {url}, model={model}")

    _log("=== GRS AI REQUEST ===")
    _log(f"URL: {url}")
    _log(f"Model: {model}")

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT,
        )
    except Exception:
        raise

    resp.encoding = "utf-8"

    _log(f"Status: {resp.status_code}")
    _log(f"Body: {resp.text[:1000]}")

    if not resp.ok:
        logger.error(f"GRS AI error: status={resp.status_code}, body={resp.text}")
        resp.raise_for_status()

    try:
        data = resp.json()
    except Exception:
        raise

    # GRS AI system error: {"code": -1, "msg": "system error"}
    if isinstance(data, dict) and data.get("code") is not None and data.get("code") != 0:
        raise RuntimeError(
            f"GRS AI ошибка: {data.get('msg', 'system error')} (code={data.get('code')}). Попробуйте ещё раз."
        )

    # Нет choices в ответе
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise RuntimeError(f"GRS AI вернул неожиданный ответ: {str(data)[:200]}")

    message = choices[0].get("message", {})
    content = message.get("content")

    if not content or not content.strip():
        usage = data.get("usage", {})
        logger.error("GRS AI returned empty content. usage=%s", usage)
        raise RuntimeError(
            "GRS AI вернул пустой ответ (0 токенов). Попробуйте ещё раз или уменьшите объём переписки."
        )

    return content.strip()
