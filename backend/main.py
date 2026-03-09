# FastAPI app

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import database
from backend.models import Lead

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


# Статика фронтенда по корневому пути (подключать после /api)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
