# Avito Messenger API client

import os
import time
import logging
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BASE_URL = "https://api.avito.ru"


class AvitoClient:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        self.client_id = (client_id or os.getenv("AVITO_CLIENT_ID") or "").strip()
        self.client_secret = (client_secret or os.getenv("AVITO_CLIENT_SECRET") or "").strip()
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._user_id: str | None = None
        self._self_data: dict | None = None

    def get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        if not self.client_id or not self.client_secret:
            raise ValueError("AVITO_CLIENT_ID and AVITO_CLIENT_SECRET must be set in .env")
        resp = requests.post(
            f"{BASE_URL}/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = time.time() + expires_in
        if not self._token:
            raise ValueError("No access_token in Avito response")
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get_token()}"}

    def get_self(self) -> dict[str, Any]:
        if self._self_data is not None:
            return self._self_data
        resp = requests.get(
            f"{BASE_URL}/core/v1/accounts/self",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._self_data = data
        self._user_id = str(data.get("id", "")) if data.get("id") is not None else None
        return data

    @property
    def user_id(self) -> str | None:
        if self._user_id is None:
            try:
                self.get_self()
            except Exception:
                pass
        return self._user_id

    def get_chats(self, limit: int = 100) -> list[dict]:
        uid = self.user_id
        if not uid:
            raise ValueError("user_id not available")
        resp = requests.get(
            f"{BASE_URL}/messenger/v2/accounts/{uid}/chats",
            headers=self._headers(),
            params={"limit": limit},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        chats = data.get("chats") if isinstance(data, dict) else None
        return list(chats) if isinstance(chats, list) else []

    def get_messages(self, chat_id: str | int, limit: int = 100) -> list[dict]:
        uid = self.user_id
        if not uid:
            raise ValueError("user_id not available")
        resp = requests.get(
            f"{BASE_URL}/messenger/v3/accounts/{uid}/chats/{chat_id}/messages/",
            headers=self._headers(),
            params={"limit": limit},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("messages") if isinstance(data, dict) else None
        return list(messages) if isinstance(messages, list) else []

    def send_message(self, chat_id: str | int, text: str) -> dict:
        uid = self.user_id
        if not uid:
            raise ValueError("user_id not available")
        resp = requests.post(
            f"{BASE_URL}/messenger/v1/accounts/{uid}/chats/{chat_id}/messages",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"type": "text", "message": {"text": text}},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def get_chat_by_id(self, chat_id: str) -> dict[str, Any]:
        uid = self.user_id
        if not uid:
            raise ValueError("user_id not available")
        resp = requests.get(
            f"{BASE_URL}/messenger/v2/accounts/{uid}/chats/{chat_id}",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def register_webhook(self, url: str) -> dict[str, Any]:
        resp = requests.post(
            f"{BASE_URL}/messenger/v3/webhook",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"url": url},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {"ok": True}
