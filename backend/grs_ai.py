# GRS AI API client for CRM (config from project .env only)

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from CRM project root
_CRM_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_CRM_ROOT / ".env")

DEFAULT_MODEL = "gpt-4o-mini"
# Таймаут запроса к GRS AI (сек). Через .env: GRS_AI_TIMEOUT=180
TIMEOUT = int(os.getenv("GRS_AI_TIMEOUT", "180"))


def _get_config():
    key = os.getenv("GRS_AI_API_KEY")
    url = (os.getenv("GRS_AI_API_URL") or "https://grsaiapi.com").rstrip("/")
    return key, url


def chat_completion(messages: list[dict], model: str | None = None, max_tokens: int | None = None) -> str:
    """
    Send messages to GRS AI Chat Completions API, return assistant text.
    messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    key, base_url = _get_config()
    if not key:
        raise ValueError("GRS_AI_API_KEY is not set in .env")

    endpoint = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    resp = requests.post(
        endpoint,
        json=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        timeout=TIMEOUT,
    )
    resp.encoding = "utf-8"
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") is not None and data.get("code") != 0:
        raise RuntimeError(data.get("msg", "GRS AI API error"))

    text = ""
    # OpenAI-style
    choices = data.get("choices")
    if choices and len(choices) > 0:
        first = choices[0]
        msg = first.get("message") or first
        text = (msg.get("content") or msg.get("text") or "").strip()
    if not text and isinstance(data.get("data"), dict):
        d = data["data"]
        out = d.get("output")
        if isinstance(out, dict):
            text = (out.get("text") or out.get("content") or "").strip()
        elif isinstance(out, str):
            text = out.strip()
        if not text:
            text = (d.get("text") or d.get("content") or d.get("message") or "").strip()
    if not text and isinstance(data.get("data"), str):
        text = data["data"].strip()
    if not text:
        text = (
            data.get("output_text")
            or data.get("response")
            or data.get("content")
            or data.get("text")
            or data.get("result")
            or data.get("message")
            or ""
        )
        if isinstance(text, str):
            text = text.strip()
        else:
            text = ""
    if not text:
        keys = list(data.keys()) if isinstance(data, dict) else []
        raise RuntimeError(
            "Empty response from GRS AI. Response keys: " + ", ".join(str(k) for k in keys[:15])
        )
    return text
