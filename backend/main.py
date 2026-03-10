# FastAPI app

import logging
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import database
from backend.models import Lead, NoteCreate, MessageCreate, MessageBulkItem, MessageDirectionUpdate
from backend import grs_ai

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
    database.update_lead(lead_id, lead)
    return database.get_lead_by_id(lead_id)


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    database.delete_lead(lead_id)
    return {"ok": True}


@app.get("/api/leads/{lead_id}/notes")
def list_notes(lead_id: int):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return database.get_notes_by_lead_id(lead_id)


@app.post("/api/leads/{lead_id}/notes")
def create_note(lead_id: int, body: NoteCreate):
    if database.get_lead_by_id(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    note_id = database.create_note(lead_id, body)
    created = database.get_note_by_id(note_id)
    return created


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


# Статика фронтенда по корневому пути (подключать после /api)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
