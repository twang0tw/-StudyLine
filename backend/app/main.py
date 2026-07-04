"""FastAPI entrypoint for the StudyLine backend.

This file should stay small:
- create the FastAPI app
- register routes
- call service-layer functions

Business logic should live in `app/services/`, not directly in route handlers.
"""

from fastapi import FastAPI
from typing import Dict

from app.services.scheduling_service import slot_id_for

app = FastAPI(title="StudyLine API")


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Simple route to confirm the backend is running."""

    return {"status": "ok"}


@app.get("/api/debug/slot-id")
def debug_slot_id(date: str, start_time: str) -> Dict[str, str]:
    """Example route that uses a service function.

    This is intentionally tiny so you can learn the pattern:
    route -> service -> response
    """

    return {
        "date": date,
        "start_time": start_time,
        "slot_id": slot_id_for(date=date, start_time=start_time),
    }
