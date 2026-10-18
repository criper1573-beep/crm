"""Пересылка вебхука Авито ассистенту. Секреты хука в тест не зашиты — только подставные маркеры."""

import logging
import sqlite3

import pytest
import requests
from fastapi.testclient import TestClient

CLIENT_AUTHOR = 424242
OWN_AUTHOR = 327789616
CREATED = 1710000000  # 2024-03-09 16:00:00 UTC = 19:00:00 MSK
MSK = "2024-03-09 19:00:00"


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    db_path = tmp_path / "crm.db"
    monkeypatch.setenv("CRM_FILES_DIR", str(tmp_path / "files"))
    import backend.database as database

    monkeypatch.setattr(database, "DB_PATH", db_path)
    return db_path


@pytest.fixture()
def client(storage, monkeypatch):
    monkeypatch.delenv("CRM_BASIC_USER", raising=False)
    monkeypatch.delenv("CRM_BASIC_PASSWORD", raising=False)
    monkeypatch.delenv("SONYA_HOOK_URL", raising=False)
    monkeypatch.delenv("SONYA_HOOK_AUTH", raising=False)
    from backend import sonya_hook
    from backend.main import app

    sonya_hook.clear_seen_message_ids()
    with TestClient(app) as test_client:
        yield test_client
    sonya_hook.clear_seen_message_ids()


def _event(
    *,
    msg_id: str,
    chat_id: str,
    author_id,
    msg_type: str = "text",
    text: str | None = "Здравствуйте",
    created: int | None = CREATED,
    user_id: int = OWN_AUTHOR,
    content: dict | None = None,
) -> dict:
    if content is None:
        content = {} if text is None else {"text": text}
    value = {
        "id": msg_id,
        "chat_id": chat_id,
        "user_id": user_id,
        "author_id": author_id,
        "type": msg_type,
        "content": content,
    }
    if created is not None:
        value["created"] = created
    return {
        "id": f"wh-{msg_id}",
        "version": "v3.0.0",
        "timestamp": created,
        "payload": {"type": "message", "value": value},
    }


def _enable(monkeypatch, auth: str = "test-auth") -> str:
    url = "http://sonya.invalid/hook"
    monkeypatch.setenv("SONYA_HOOK_URL", url)
    monkeypatch.setenv("SONYA_HOOK_AUTH", auth)
    return url


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code


def _patch_post(monkeypatch, statuses=(200,)):
    calls = []
    seq = list(statuses)

    def fake(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        code = seq.pop(0) if seq else statuses[-1]
        return _Resp(code)

    monkeypatch.setattr("backend.sonya_hook.requests.post", fake)
    return calls


def _counts(db_path) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    finally:
        conn.close()
    return leads, messages


def _lead_id(client: TestClient, chat_id: str) -> int:
    rows = [row for row in client.get("/api/leads").json() if row.get("avito_chat_id") == chat_id]
    assert len(rows) == 1
    return rows[0]["id"]


def test_avito_webhook_returns_200_when_sonya_unreachable(client, storage, monkeypatch, caplog):
    auth = "do-not-log-this-marker"
    _enable(monkeypatch, auth=auth)
    calls = {"n": 0}

    def fail(url, **kwargs):
        calls["n"] += 1
        assert kwargs["timeout"] == 5
        assert kwargs["headers"]["Authorization"] == auth
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr("backend.sonya_hook.requests.post", fail)
    body = _event(msg_id="unreachable-1", chat_id="chat-unreachable", author_id=CLIENT_AUTHOR)

    with caplog.at_level(logging.ERROR):
        response = client.post("/api/avito/webhook", json=body)

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls["n"] == 2
    assert _counts(storage) == (1, 1)
    assert auth not in caplog.text
    errors = [record for record in caplog.records if record.name == "backend.sonya_hook"]
    assert len(errors) == 1
    assert "ConnectionError" in errors[0].message


def test_without_sonya_env_there_is_no_outgoing_request(client, storage, monkeypatch):
    calls = []

    def blocked(self, method, url, *args, **kwargs):
        calls.append((method, url))
        raise AssertionError(f"unexpected outgoing {method} {url}")

    monkeypatch.setattr("requests.sessions.Session.request", blocked)
    cases = [
        {},
        {"SONYA_HOOK_URL": "http://sonya.invalid/hook"},
        {"SONYA_HOOK_AUTH": "test-auth"},
        {"SONYA_HOOK_URL": "   ", "SONYA_HOOK_AUTH": "test-auth"},
        {"SONYA_HOOK_URL": "http://sonya.invalid/hook", "SONYA_HOOK_AUTH": "   "},
    ]
    for index, env in enumerate(cases):
        monkeypatch.delenv("SONYA_HOOK_URL", raising=False)
        monkeypatch.delenv("SONYA_HOOK_AUTH", raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        response = client.post(
            "/api/avito/webhook",
            json=_event(msg_id=f"noenv-{index}", chat_id=f"chat-noenv-{index}", author_id=CLIENT_AUTHOR),
        )
        assert response.status_code == 200
    assert calls == []
    assert _counts(storage) == (len(cases), len(cases))


def test_duplicate_event_does_not_create_second_lead_or_forward(client, storage, monkeypatch):
    url = _enable(monkeypatch)
    calls = _patch_post(monkeypatch)
    body = _event(msg_id="dup-1", chat_id="chat-dup", author_id=CLIENT_AUTHOR, text="Первое")

    first = client.post("/api/avito/webhook", json=body)
    second = client.post("/api/avito/webhook", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert _counts(storage) == (1, 1)
    assert len(calls) == 1
    sent = calls[0]["kwargs"]["json"]
    assert calls[0]["url"] == url
    assert sent["lead_created"] is True
    assert sent["lead_id"] == _lead_id(client, "chat-dup")
    assert sent["text"] == "Первое"
    messages = client.get(f"/api/leads/{sent['lead_id']}/messages").json()
    assert len(messages) == 1
    assert messages[0]["text"] == "Первое"


def test_call_is_not_stored_but_is_forwarded(client, storage, monkeypatch):
    url = _enable(monkeypatch)
    calls = _patch_post(monkeypatch)
    body = _event(
        msg_id="call-1",
        chat_id="chat-call",
        author_id=CLIENT_AUTHOR,
        msg_type="call",
        text=None,
        content={"call": {"status": "missed"}},
    )

    response = client.post("/api/avito/webhook", json=body)

    assert response.status_code == 200
    assert _counts(storage) == (0, 0)
    assert len(calls) == 1
    sent = calls[0]["kwargs"]["json"]
    assert calls[0]["url"] == url
    assert sent["source"] == "avito"
    assert sent["webhook_event"] == body
    assert sent["lead_id"] is None
    assert sent["lead_created"] is False
    assert sent["chat_id"] == "chat-call"
    assert sent["author_id"] == CLIENT_AUTHOR
    assert sent["message_type"] == "call"
    assert sent["created_at_msk"] == MSK
    assert "text" not in sent
    assert calls[0]["kwargs"]["headers"]["Content-Type"] == "application/json"
    assert calls[0]["kwargs"]["headers"]["Authorization"] == "test-auth"
    assert calls[0]["kwargs"]["timeout"] == 5


def test_call_on_existing_chat_keeps_lead_and_forwards_its_id(client, storage, monkeypatch):
    _enable(monkeypatch)
    calls = _patch_post(monkeypatch)
    text = _event(msg_id="text-before-call", chat_id="chat-known", author_id=CLIENT_AUTHOR, text="Жду звонка")
    call = _event(
        msg_id="call-known",
        chat_id="chat-known",
        author_id=CLIENT_AUTHOR,
        msg_type="call",
        text=None,
    )

    assert client.post("/api/avito/webhook", json=text).status_code == 200
    assert client.post("/api/avito/webhook", json=call).status_code == 200

    assert _counts(storage) == (1, 1)
    assert len(calls) == 2
    lead_id = _lead_id(client, "chat-known")
    assert calls[1]["kwargs"]["json"]["lead_id"] == lead_id
    assert calls[1]["kwargs"]["json"]["lead_created"] is False
    assert calls[1]["kwargs"]["json"]["message_type"] == "call"
    assert "text" not in calls[1]["kwargs"]["json"]


def test_own_author_message_is_not_forwarded(client, storage, monkeypatch):
    _enable(monkeypatch)
    calls = _patch_post(monkeypatch)
    body = _event(
        msg_id="own-1",
        chat_id="chat-own",
        author_id=OWN_AUTHOR,
        text="Ответ менеджера",
    )
    again = _event(
        msg_id="own-2",
        chat_id="chat-own",
        author_id=str(OWN_AUTHOR),
        text="Ещё наш ответ",
        created=CREATED + 60,
    )

    assert client.post("/api/avito/webhook", json=body).status_code == 200
    assert client.post("/api/avito/webhook", json=again).status_code == 200

    assert calls == []
    assert _counts(storage) == (1, 2)
    lead_id = _lead_id(client, "chat-own")
    messages = client.get(f"/api/leads/{lead_id}/messages").json()
    assert [row["text"] for row in messages] == ["Ответ менеджера", "Ещё наш ответ"]
    assert {row["direction"] for row in messages} == {"out"}


def test_system_author_is_not_forwarded(client, storage, monkeypatch):
    _enable(monkeypatch)
    calls = _patch_post(monkeypatch)
    body = _event(msg_id="sys-1", chat_id="chat-sys", author_id=0, text="Системное")

    assert client.post("/api/avito/webhook", json=body).status_code == 200

    assert calls == []
    assert _counts(storage) == (1, 1)


def test_message_without_text_is_forwarded_and_not_stored(client, storage, monkeypatch):
    _enable(monkeypatch)
    calls = _patch_post(monkeypatch)
    body = _event(
        msg_id="image-1",
        chat_id="chat-image",
        author_id=CLIENT_AUTHOR,
        msg_type="image",
        text=None,
        content={"image": {"sizes": {}}},
    )

    assert client.post("/api/avito/webhook", json=body).status_code == 200

    assert _counts(storage) == (0, 0)
    assert len(calls) == 1
    sent = calls[0]["kwargs"]["json"]
    assert sent["message_type"] == "image"
    assert sent["lead_id"] is None
    assert sent["lead_created"] is False
    assert "text" not in sent


def test_client_text_forward_body_and_second_message(client, monkeypatch):
    _enable(monkeypatch)
    calls = _patch_post(monkeypatch)
    first = _event(msg_id="text-1", chat_id="chat-text", author_id=CLIENT_AUTHOR, text="Нужна кухня")
    second = _event(
        msg_id="text-2",
        chat_id="chat-text",
        author_id=CLIENT_AUTHOR,
        text="И замер",
        created=CREATED + 60,
    )

    assert client.post("/api/avito/webhook", json=first).status_code == 200
    assert client.post("/api/avito/webhook", json=second).status_code == 200

    assert len(calls) == 2
    lead_id = _lead_id(client, "chat-text")
    assert calls[0]["kwargs"]["json"]["lead_id"] == lead_id
    assert calls[0]["kwargs"]["json"]["lead_created"] is True
    assert calls[0]["kwargs"]["json"]["webhook_event"] == first
    assert calls[0]["kwargs"]["json"]["created_at_msk"] == MSK
    assert calls[0]["kwargs"]["json"]["author_id"] == CLIENT_AUTHOR
    assert calls[0]["kwargs"]["json"]["chat_id"] == "chat-text"
    assert calls[1]["kwargs"]["json"]["lead_id"] == lead_id
    assert calls[1]["kwargs"]["json"]["lead_created"] is False
    assert calls[1]["kwargs"]["json"]["text"] == "И замер"
    messages = client.get(f"/api/leads/{lead_id}/messages").json()
    assert [row["text"] for row in messages] == ["Нужна кухня", "И замер"]


def test_sonya_retries_once_on_5xx_and_not_on_4xx(client, monkeypatch, caplog):
    _enable(monkeypatch, auth="do-not-log-this-marker")
    calls = _patch_post(monkeypatch, statuses=(502, 200))
    ok = _event(msg_id="retry-ok", chat_id="chat-retry", author_id=CLIENT_AUTHOR, text="Повтор")

    with caplog.at_level(logging.ERROR, logger="backend.sonya_hook"):
        assert client.post("/api/avito/webhook", json=ok).status_code == 200
    assert len(calls) == 2
    assert [record for record in caplog.records if record.name == "backend.sonya_hook"] == []

    caplog.clear()
    calls = _patch_post(monkeypatch, statuses=(400,))
    denied = _event(msg_id="retry-400", chat_id="chat-retry-400", author_id=CLIENT_AUTHOR, text="Четыреста")
    with caplog.at_level(logging.ERROR, logger="backend.sonya_hook"):
        assert client.post("/api/avito/webhook", json=denied).status_code == 200
    assert len(calls) == 1
    errors = [record for record in caplog.records if record.name == "backend.sonya_hook"]
    assert len(errors) == 1
    assert "HTTP 400" in errors[0].message
    assert "do-not-log-this-marker" not in caplog.text


def test_repeated_call_is_forwarded_once(client, storage, monkeypatch):
    _enable(monkeypatch)
    calls = _patch_post(monkeypatch)
    body = _event(msg_id="call-dup", chat_id="chat-call-dup", author_id=CLIENT_AUTHOR, msg_type="call", text=None)

    assert client.post("/api/avito/webhook", json=body).status_code == 200
    assert client.post("/api/avito/webhook", json=body).status_code == 200

    assert len(calls) == 1
    assert _counts(storage) == (0, 0)
