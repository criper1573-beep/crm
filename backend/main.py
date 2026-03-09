# FastAPI app

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
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _normalize_summary_text(text: str) -> str:
    """Убирает переносы внутри строк (от API), оставляет только абзацы."""
    if not text or not text.strip():
        return text
    import re
    # Сохраняем разбиение на абзацы (двойной перенос)
    placeholder = "\x00\x00"
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\n{2,}", placeholder, t)
    # Одиночные \n -> пробел
    t = t.replace("\n", " ")
    t = t.replace(placeholder, "\n\n")
    # Убрать лишние пробелы и переносы по краям
    t = re.sub(r" +", " ", t).strip()
    return t


@app.on_event("startup")
def startup():
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
        messages_api = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        summary = grs_ai.chat_completion(messages_api, max_tokens=800)
        summary = _normalize_summary_text(summary or "")

        lead_dict = database.get_lead_by_id(lead_id)
        if lead_dict:
            lead_dict["description"] = summary
            lead_obj = Lead(**{k: v for k, v in lead_dict.items() if k in Lead.model_fields})
            database.update_lead(lead_id, lead_obj)
    except Exception as e:
        # Логируем; ответ клиенту уже отправлен (202)
        import logging
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


# Статика фронтенда по корневому пути (подключать после /api)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
