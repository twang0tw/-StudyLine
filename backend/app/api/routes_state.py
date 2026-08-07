from random import random, randrange
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Query

from app.services import state_service
from app.services.db_service import app_state

router = APIRouter(tags=["state"])


def _selected_slot_id(slot_id: Optional[str]) -> Optional[str]:
    if slot_id:
        return slot_id
    return app_state["availability"][0]["id"] if app_state["availability"] else None


@router.get("/api/state")
def get_state(
    student_id: Optional[str] = Query(default=None, alias="studentId"),
    slot_id: Optional[str] = Query(default=None, alias="slotId"),
):
    return state_service.build_state(
        slots=app_state["availability"],
        availability=app_state["availability"],
        queue_entries=app_state["queue"],
        current_by_slot=app_state["currentBySlot"],
        served_by_slot=app_state["servedBySlot"],
        student_id=student_id,
        requested_slot_id=slot_id,
        tas_active=app_state["tasActive"],
        avg_help_minutes=app_state["averageHelpMinutes"],
        forecast=app_state["forecast"],
    )


@router.post("/api/simulate-crowd")
def simulate_crowd(
    slot_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None, alias="studentId"),
):
    selected_slot_id = _selected_slot_id(slot_id)
    app_state["tasActive"] = 3 if random() > 0.78 else 2
    app_state["averageHelpMinutes"] = 6 + randrange(4)

    if selected_slot_id and random() > 0.5:
        app_state["queue"].append(
            {
                "id": str(uuid4()),
                "slotId": selected_slot_id,
                "name": "Walk-in Student",
                "course": "General",
                "need": "Quick question",
                "message": "Short walk-in question.",
                "file": None,
                "ai": {
                    "summary": "Short walk-in question.",
                    "estimatedHelpMinutes": 5,
                    "confidence": "low",
                    "source": "simulation",
                },
                "status": "waiting",
            }
        )
    elif selected_slot_id and len(app_state["queue"]) > 1:
        remove_index = next(
            (
                index
                for index, entry in enumerate(app_state["queue"])
                if entry.get("slotId") == selected_slot_id
            ),
            None,
        )
        if remove_index is not None:
            app_state["queue"].pop(remove_index)

    return get_state(student_id=student_id, slot_id=selected_slot_id)
