# FastAPI app

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import database
from backend.models import Lead, NoteCreate, MessageCreate, MessageBulkItem, MessageDirectionUpdate

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


# Статика фронтенда по корневому пути (подключать после /api)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
