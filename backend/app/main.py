"""FastAPI entrypoint for the StudyLine backend.

This file should stay small:
- create the FastAPI app
- register routes
- call service-layer functions

Business logic should live in `app/services/`, not directly in route handlers.
"""

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Dict

from app.services import db_service
from app.services import scheduling_service
from app.api import routes_queue, routes_slots, routes_state, routes_ta

app = FastAPI(title="StudyLine API")

app.include_router(routes_slots.router)
app.include_router(routes_queue.router)
app.include_router(routes_state.router)
app.include_router(routes_ta.router)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FRONTEND_FILES = {
    "index.html",
    "student.html",
    "ta.html",
    "app.js",
    "styles.css",
}


@app.on_event("startup")
def startup() -> None:
    db_service.initialize_database()


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Simple route to confirm the backend is running."""

    return {"status": "ok"}


@app.get("/")
def home_page():
    return FileResponse(PROJECT_ROOT / "index.html")


@app.get("/{file_name}")
def frontend_file(file_name: str):
    if file_name not in ALLOWED_FRONTEND_FILES:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(PROJECT_ROOT / file_name)


@app.get("/api/debug/slot-id")
def debug_slot_id(date: str, start_time: str) -> Dict[str, str]:
    """Example route that uses a service function.

    This is intentionally tiny so you can learn the pattern:
    route -> service -> response
    """

    return {
        "date": date,
        "start_time": start_time,
        "slot_id": scheduling_service.slot_id_for(date=date, start_time=start_time),
    }
