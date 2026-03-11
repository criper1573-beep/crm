# FastAPI app

import logging
from datetime import datetime as _dt
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import database
from backend.models import Lead, LeadObjectCreate, NoteCreate, MessageCreate, MessageBulkItem, MessageDirectionUpdate, AvitoSendMessage, AvitoRegisterWebhook
from backend import grs_ai
from backend import avito

app = FastAPI()

# CORS для локального фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Путь к папке frontend (от корня проекта)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
LOG_FILE = PROJECT_ROOT / "crm.log"


class _FlushingFileHandler(logging.FileHandler):
    """Пишет в файл и сразу сбрасывает буфер — логи видны без перезапуска."""

    def emit(self, record):
        super().emit(record)
        self.flush()


def _normalize_summary_text(text: str) -> str:
    """Убирает переносы внутри строк (артефакты GRS AI), оставляет только настоящие абзацы.

    Настоящий разрыв абзаца = \n\n, где перед ним идёт завершение предложения (. ! ?).
    Все остальные переносы (включая \n\n посреди предложения) заменяются пробелом.
    """
    if not text or not text.strip():
        return text
    import re
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # Все \n (любое количество) → пробел; потом восстановим настоящие абзацы
    # Шаг 1: Пометить настоящие разрывы абзацев: \n\n после [.!?] (с возможными пробелами)
    REAL_PARA = "\x00\x00"
    t = re.sub(r'([.!?])\s*\n{2,}', r'\1' + REAL_PARA, t)
    # Шаг 2: Все оставшиеся переносы (в т.ч. \n\n посреди предложений) → пробел
    t = re.sub(r'\n+', ' ', t)
    # Шаг 3: Восстановить настоящие абзацы
    t = t.replace(REAL_PARA, "\n\n")
    # Убрать лишние пробелы
    t = re.sub(r' {2,}', ' ', t)
    t = re.sub(r'\n\n +', '\n\n', t)
    # Убрать пробелы перед знаками препинания (артефакты GRS AI: " ," " .")
    t = re.sub(r' +([.,!?;:])', r'\1', t)
    return t.strip()


@app.on_event("startup")
def startup():
    # Логи в файл в корне проекта, сброс после каждой записи
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = _FlushingFileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Один handler на backend — все backend.* (grs_ai, main) пишут сюда
    backend_log = logging.getLogger("backend")
    backend_log.addHandler(file_handler)
    backend_log.setLevel(logging.INFO)

    logging.getLogger("backend.main").info("CRM started, logs: %s", LOG_FILE)

    database.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/leads")
def list_leads():
    return database.get_all_leads()


@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: int):
    lead = database.get_lead_by_id(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.get("has_multiple_objects"):
        lead["objects"] = database.get_objects_by_lead_id(lead_id)
    else:
        lead["objects"] = []
    return lead


@app.post("/api/leads")
def create_lead(lead: Lead):
    new_id = database.create_lead(lead)
    created = database.get_lead_by_id(new_id)
    return created


@app.put("/api/leads/{lead_id}")
def update_lead(lead_id: int, lead: Lead):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    prev = database.get_lead_by_id(lead_id)
    database.update_lead(lead_id, lead)
    if getattr(lead, "has_multiple_objects", False) and not (prev and prev.get("has_multiple_objects")):
        objs = database.get_objects_by_lead_id(lead_id)
        if not objs:
            database.migrate_lead_to_first_object(lead_id)
    updated = database.get_lead_by_id(lead_id)
    if updated.get("has_multiple_objects"):
        updated["objects"] = database.get_objects_by_lead_id(lead_id)
    else:
        updated["objects"] = []
    return updated


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    database.delete_lead(lead_id)
    return {"ok": True}


@app.get("/api/leads/{lead_id}/notes")
def list_notes(lead_id: int, lead_object_id: int | None = None):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return database.get_notes_by_lead_id(lead_id, lead_object_id=lead_object_id)


@app.post("/api/leads/{lead_id}/notes")
def create_note(lead_id: int, body: NoteCreate):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    note_id = database.create_note(lead_id, body, lead_object_id=getattr(body, "lead_object_id", None))
    created = database.get_note_by_id(note_id)
    return created


@app.get("/api/leads/{lead_id}/objects")
def list_objects(lead_id: int):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return database.get_objects_by_lead_id(lead_id)


@app.post("/api/leads/{lead_id}/objects")
def create_object(lead_id: int, body: LeadObjectCreate):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    obj_id = database.create_lead_object(lead_id, body)
    return database.get_object_by_id(obj_id)


@app.put("/api/leads/{lead_id}/objects/{object_id}")
def update_object(lead_id: int, object_id: int, body: LeadObjectCreate | dict):
    obj = database.get_object_by_id(object_id)
    if obj is None or obj.get("lead_id") != lead_id:
        raise HTTPException(status_code=404, detail="Object not found")
    database.update_lead_object(object_id, body)
    return database.get_object_by_id(object_id)


@app.delete("/api/leads/{lead_id}/objects/{object_id}")
def delete_object(lead_id: int, object_id: int):
    obj = database.get_object_by_id(object_id)
    if obj is None or obj.get("lead_id") != lead_id:
        raise HTTPException(status_code=404, detail="Object not found")
    database.delete_lead_object(object_id)
    return {"ok": True}


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: int):
    ok = database.delete_note(note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


@app.get("/api/leads/{lead_id}/messages")
def list_messages(lead_id: int):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return database.get_messages_by_lead_id(lead_id)


@app.post("/api/leads/{lead_id}/messages")
def create_message(lead_id: int, body: MessageCreate):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    msg_id = database.create_message(lead_id, body)
    return database.get_message_by_id(msg_id)


@app.post("/api/leads/{lead_id}/messages/bulk")
def create_messages_bulk(lead_id: int, body: list[MessageBulkItem]):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    database.create_messages_bulk(lead_id, body)
    return database.get_messages_by_lead_id(lead_id)


@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int):
    ok = database.delete_message(message_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}


@app.patch("/api/messages/{message_id}/direction")
def update_message_direction(message_id: int, body: MessageDirectionUpdate):
    if body.direction not in ("in", "out"):
        raise HTTPException(status_code=400, detail="direction must be 'in' or 'out'")
    direction = body.direction
    ok = database.update_message_direction(message_id, direction)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return database.get_message_by_id(message_id)


def _run_summarize(lead_id: int) -> None:
    """Фоновая задача: запрос к GRS AI и сохранение описания в БД. Результат сохраняется даже при закрытии вкладки."""
    try:
        lead = database.get_lead_by_id(lead_id)
        if lead is None:
            return
        notes = database.get_notes_by_lead_id(lead_id)
        messages = database.get_messages_by_lead_id(lead_id)

        context_path = Path(__file__).resolve().parent.parent / "data" / "context.txt"
        context_text = ""
        if context_path.exists():
            context_text = context_path.read_text(encoding="utf-8", errors="replace").strip()

        system_content = (context_text + "\n\n" if context_text else "") + (
            "Сформируй краткое резюме по переписке и заметкам для карточки лида: 1–2 абзаца, "
            "суть запроса клиента и договорённостей. Пиши только текст резюме, без заголовков."
        )

        parts = []
        for m in messages:
            dt = (m.get("created_at") or "")[:16]
            direction = (m.get("direction") or "").strip()
            source = (m.get("source") or "").strip()
            label = f"[{dt}] {direction} ({source}): " if (dt or direction or source) else ""
            parts.append(f"{label}{m.get('text', '')}")
        for n in notes:
            dt = (n.get("created_at") or "")[:16]
            label = f"[Заметка {dt}]: " if dt else "[Заметка]: "
            parts.append(f"{label}{n.get('text', '')}")

        user_content = "\n\n".join(parts) if parts else "Нет переписки и заметок."

        # Если контент слишком большой — обрезаем до 12 000 символов (~ 3 000 токенов)
        MAX_CHARS = 12_000
        if len(user_content) > MAX_CHARS:
            user_content = user_content[-MAX_CHARS:]  # берём последние (самые свежие)

        messages_api = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        # Авторетрай до 3 раз с паузой 5 сек при пустом ответе от GRS AI
        import time as _time_retry
        summary = None
        last_err = None
        for _attempt in range(3):
            try:
                summary = grs_ai.chat_completion(messages_api, max_tokens=800)
                break
            except RuntimeError as _re:
                last_err = _re
                logging.getLogger("backend.main").warning(
                    "Summarize lead %s attempt %d failed: %s", lead_id, _attempt + 1, _re)
                if _attempt < 2:
                    _time_retry.sleep(5)
        if summary is None:
            raise last_err
        summary = _normalize_summary_text(summary or "")

        lead_dict = database.get_lead_by_id(lead_id)
        if lead_dict:
            lead_dict["description"] = summary
            lead_obj = Lead(**{k: v for k, v in lead_dict.items() if k in Lead.model_fields})
            database.update_lead(lead_id, lead_obj)
    except Exception as e:
        logging.getLogger("backend.main").exception("Summarize lead %s: %s", lead_id, e)


@app.post("/api/leads/{lead_id}/summarize")
def summarize_lead(lead_id: int, background_tasks: BackgroundTasks):
    lead = database.get_lead_by_id(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    background_tasks.add_task(_run_summarize, lead_id)
    return JSONResponse(
        status_code=202,
        content={"status": "started", "message": "Резюме генерируется в фоне. Результат сохранится в описание лида."},
    )


@app.post("/api/leads/{lead_id}/generate-reply")
def generate_reply(lead_id: int):
    """Генерация ответа клиенту по последним 10 сообщениям и контексту. Синхронно."""
    # #region agent log
    import json as _j
    _dbg_path = PROJECT_ROOT / "debug-8d7168.log"
    try:
        with open(_dbg_path, "a", encoding="utf-8") as _f:
            _f.write(_j.dumps({"sessionId": "8d7168", "location": "main.py:generate_reply", "message": "handler hit", "data": {"lead_id": lead_id}, "hypothesisId": "H3", "timestamp": __import__("time").time() * 1000}) + "\n")
    except Exception:
        pass
    # #endregion
    lead = database.get_lead_by_id(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Лид не найден")
    messages = database.get_messages_by_lead_id(lead_id)
    last_10 = messages[-10:] if len(messages) > 10 else messages

    context_path = PROJECT_ROOT / "data" / "context.txt"
    context_text = ""
    if context_path.exists():
        context_text = context_path.read_text(encoding="utf-8", errors="replace").strip()
    description = (lead.get("description") or "").strip()

    system_content = (
        "Ты помощник менеджера по ремонту коммерческих помещений.\n"
        f"Контекст бизнеса: {context_text}\n"
        f"Описание проекта: {description}\n"
        "Задача: напиши короткий деловой ответ клиенту на русском языке.\n"
        "Только текст ответа, без кавычек и пояснений."
    )
    user_lines = [f"[{m.get('direction', '')}]: {m.get('text', '')}" for m in last_10]
    user_content = "\n".join(user_lines) if user_lines else "Нет сообщений."

    messages_api = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    try:
        reply = grs_ai.chat_completion(messages_api, max_tokens=300)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    reply = _normalize_summary_text(reply.strip() or "")
    return {"reply": reply}


_avito_client: avito.AvitoClient | None = None


def _get_avito_client() -> avito.AvitoClient:
    global _avito_client
    if _avito_client is None:
        _avito_client = avito.AvitoClient()
    return _avito_client


@app.get("/api/avito/self")
def avito_self():
    """Проверка подключения Авито: user_id и имя аккаунта."""
    try:
        client = _get_avito_client()
        data = client.get_self()
        user_id = data.get("id")
        name = data.get("name") or data.get("profile", {}).get("name") or ""
        return {"user_id": str(user_id) if user_id is not None else None, "name": name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.getLogger("backend.main").exception("Avito self: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


def _load_avito_chat_history(lead_id: int, chat_id: str) -> None:
    """Фоновая задача: подгрузить историю чата Авито в переписку CRM при создании нового лида."""
    log = logging.getLogger("backend.main")
    try:
        client = _get_avito_client()
        # Попытаться получить имя клиента и ссылку на объявление из данных чата
        try:
            chat = client.get_chat_by_id(chat_id)
            my_user_id = str(client.user_id or "")
            users = chat.get("users") or []
            other_user = next(
                (u for u in users if str(u.get("id", "")) != my_user_id),
                None,
            )
            if other_user:
                name = (other_user.get("name") or "").strip()
                profile = other_user.get("public_user_profile") or {}
                avito_link = (profile.get("url") or "").strip()
                database.update_lead_avito_info(lead_id, name=name or None, avito_link=avito_link or None)
            context = chat.get("context") or {}
            ctx_value = context.get("value") or {}
            item_url = (ctx_value.get("url") or "").strip()
            if item_url:
                database.update_lead_avito_info(lead_id, avito_link=item_url)
        except Exception as e:
            log.warning("Avito get_chat_by_id for chat %s: %s", chat_id, e)

        # Загрузить сообщения из чата
        messages = client.get_messages(chat_id, limit=100)
        my_user_id = str(client.user_id or "")
        inserted = 0
        for msg in messages:
            msg_id = str(msg.get("id") or "")
            if not msg_id:
                continue
            msg_type = msg.get("type", "")
            if msg_type not in ("text",):
                continue
            content = msg.get("content") or {}
            text = (content.get("text") or "").strip()
            if not text:
                continue
            # direction: из API сообщений, либо вычислить по author_id
            direction = msg.get("direction", "")
            if not direction:
                author_id = str(msg.get("author_id") or "")
                direction = "out" if author_id == my_user_id else "in"
            created_ts = msg.get("created")
            created_at = (
                _dt.utcfromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M:%S")
                if created_ts else None
            )
            result = database.create_avito_message(lead_id, text, direction, created_at, msg_id)
            if result is not None:
                inserted += 1
        log.info("Avito chat history loaded for lead %s, chat %s: %d messages inserted", lead_id, chat_id, inserted)
    except Exception as e:
        log.exception("Load avito chat history for lead %s, chat %s: %s", lead_id, chat_id, e)


@app.post("/api/avito/webhook")
async def avito_webhook(request: Request, background_tasks: BackgroundTasks):
    """Принимает webhook-уведомления от Авито Мессенджер."""
    log = logging.getLogger("backend.main")
    # #region agent log
    import time as _t
    _dbg_path = PROJECT_ROOT / "debug-8d7168.log"
    try:
        _raw = await request.body()
        with open(_dbg_path, "a", encoding="utf-8") as _f:
            import json as _jj
            _f.write(_jj.dumps({"sessionId": "8d7168", "location": "main.py:avito_webhook", "message": "webhook hit", "data": {"method": request.method, "raw_body": _raw.decode("utf-8", errors="replace")[:500], "headers": dict(request.headers)}, "hypothesisId": "H1-H3", "timestamp": int(_t.time() * 1000)}) + "\n")
    except Exception as _le:
        pass
    # #endregion
    try:
        body = await request.json()
    except Exception:
        # #region agent log
        try:
            with open(_dbg_path, "a", encoding="utf-8") as _f:
                _f.write(_jj.dumps({"sessionId": "8d7168", "location": "main.py:avito_webhook_parse_error", "message": "json parse failed, returning 200", "data": {}, "hypothesisId": "H3", "timestamp": int(_t.time() * 1000)}) + "\n")
        except Exception:
            pass
        # #endregion
        return JSONResponse(status_code=200, content={"ok": True})

    payload = body.get("payload") or {}
    if payload.get("type") != "message":
        return JSONResponse(status_code=200, content={"ok": True})

    value = payload.get("value") or {}
    chat_id = (value.get("chat_id") or "").strip()
    msg_id = str(value.get("id") or "").strip()
    msg_type = (value.get("type") or "").strip()

    if not chat_id or not msg_id:
        return JSONResponse(status_code=200, content={"ok": True})

    if msg_type != "text":
        return JSONResponse(status_code=200, content={"ok": True})

    content = value.get("content") or {}
    text = (content.get("text") or "").strip()
    if not text:
        return JSONResponse(status_code=200, content={"ok": True})

    author_id = str(value.get("author_id") or "")
    our_user_id = str(value.get("user_id") or "")
    direction = "out" if (author_id and author_id == our_user_id) else "in"

    created_ts = value.get("created")
    created_at = (
        _dt.utcfromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M:%S")
        if created_ts else None
    )

    lead = database.get_lead_by_avito_chat_id(chat_id)
    is_new_lead = lead is None
    if is_new_lead:
        lead_id = database.create_avito_lead(avito_chat_id=chat_id)
        log.info("New Avito lead created: lead_id=%s, chat_id=%s", lead_id, chat_id)
    else:
        lead_id = lead["id"]

    database.create_avito_message(lead_id, text, direction, created_at, msg_id)

    # #region agent log
    try:
        with open(_dbg_path, "a", encoding="utf-8") as _f:
            import json as _jj2
            _f.write(_jj2.dumps({"sessionId": "8d7168", "location": "main.py:avito_webhook_processed", "message": "message processed", "data": {"chat_id": chat_id, "msg_id": msg_id, "direction": direction, "is_new_lead": is_new_lead, "lead_id": lead_id}, "hypothesisId": "H4", "timestamp": int(_t.time() * 1000)}) + "\n")
    except Exception:
        pass
    # #endregion

    if is_new_lead:
        background_tasks.add_task(_load_avito_chat_history, lead_id, chat_id)

    return JSONResponse(status_code=200, content={"ok": True})


@app.post("/api/leads/{lead_id}/send-avito")
def send_to_avito(lead_id: int, body: AvitoSendMessage):
    """Отправить сообщение в Авито Мессенджер и сохранить в CRM."""
    lead = database.get_lead_by_id(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    avito_chat_id = (lead.get("avito_chat_id") or "").strip()
    if not avito_chat_id:
        raise HTTPException(status_code=400, detail="Этот лид не привязан к чату Авито")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст сообщения не может быть пустым")
    try:
        client = _get_avito_client()
        resp = client.send_message(avito_chat_id, text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.getLogger("backend.main").exception("send_to_avito lead %s: %s", lead_id, e)
        raise HTTPException(status_code=502, detail=str(e))

    avito_msg_id = str(resp.get("id") or "").strip()
    created_ts = resp.get("created")
    created_at = (
        _dt.utcfromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M:%S")
        if created_ts else None
    )
    if avito_msg_id:
        msg_id = database.create_avito_message(lead_id, text, "out", created_at, avito_msg_id)
    else:
        msg_id = database.create_message(lead_id, MessageCreate(text=text, direction="out", source="Авито"))
    return database.get_message_by_id(msg_id) if msg_id else {"ok": True}


@app.post("/api/leads/{lead_id}/avito-seen")
def avito_seen(lead_id: int):
    """Сбросить флаг avito_new_chat при открытии карточки лида."""
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    database.set_lead_avito_new_chat(lead_id, False)
    return {"ok": True}


@app.post("/api/avito/register-webhook")
def avito_register_webhook(body: AvitoRegisterWebhook):
    """Зарегистрировать webhook URL в Авито Мессенджер."""
    try:
        client = _get_avito_client()
        result = client.register_webhook(body.url)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.getLogger("backend.main").exception("Avito register webhook: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


# Статика фронтенда по корневому пути (подключать после /api)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
