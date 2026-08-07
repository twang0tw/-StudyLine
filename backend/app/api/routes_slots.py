from typing import Optional

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.services.db_service import app_state
from app.services.scheduling_service import create_thirty_minute_slots, crowd_level, estimate_wait
from app.services.state_service import build_state

router = APIRouter(tags=["slots"])


class CreateAvailabilityRequest(BaseModel):
    date: str
    start_time: str = Field(default="09:00", alias="start_time", max_length=5)
    end_time: str = Field(default="09:30", alias="end_time", max_length=5)
    ta_name: str = Field(default="TA", alias="ta_name", max_length=80)
    location: str = Field(default="Office Hours Room", max_length=100)

    class Config:
        allow_population_by_field_name = True


def _state(student_id: Optional[str] = None, slot_id: Optional[str] = None):
    return build_state(
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


def _waiting_for_slot(slot_id: str):
    return [
        entry
        for entry in app_state["queue"]
        if entry.get("status") == "waiting" and entry.get("slotId") == slot_id
    ]


@router.get("/api/slots")
def list_slots():
    state = _state()
    return {"slots": state["slots"]}


@router.get("/api/slots/{slot_id}/overview")
def slot_overview(slot_id: str):
    waiting = _waiting_for_slot(slot_id)
    wait = estimate_wait(
        waiting,
        tas_active=app_state["tasActive"],
        average_help_minutes=app_state["averageHelpMinutes"],
    )
    return {
        "students_waiting": len(waiting),
        "tas_active": app_state["tasActive"],
        "average_help_minutes": app_state["averageHelpMinutes"],
        "estimated_wait_minutes": wait,
        "crowd": crowd_level(wait),
    }


@router.get("/api/forecast")
def forecast(slot_id: Optional[str] = None):
    return {"forecast": app_state["forecast"]}


@router.post("/api/availability", status_code=status.HTTP_201_CREATED)
def create_availability(payload: CreateAvailabilityRequest):
    slots = create_thirty_minute_slots(
        date=payload.date[:10],
        start_time=payload.start_time[:5],
        end_time=payload.end_time[:5],
        ta_name=payload.ta_name.strip()[:80] or "TA",
        location=payload.location.strip()[:100] or "Office Hours Room",
    )
    existing_slot_ids = {slot["id"] for slot in app_state["availability"]}

    for slot in slots:
        if slot["id"] not in existing_slot_ids:
            app_state["availability"].append(slot)

    app_state["availability"].sort(key=lambda slot: f"{slot['date']}T{slot['startTime']}")
    selected_slot_id = slots[0]["id"] if slots else None

    return {"slots": slots, "state": _state(slot_id=selected_slot_id)}


@router.delete("/api/availability/{slot_id}", status_code=status.HTTP_200_OK)
def delete_availability(slot_id: str):
    len_before = len(app_state["availability"])
    app_state["availability"] = [
        slot for slot in app_state["availability"] if slot["id"] != slot_id
    ]
    app_state["queue"] = [
        entry for entry in app_state["queue"] if entry.get("slotId") != slot_id
    ]
    app_state["currentBySlot"].pop(slot_id, None)
    app_state["servedBySlot"].pop(slot_id, None)

    selected_slot_id = app_state["availability"][0]["id"] if app_state["availability"] else None
    return {
        "removed": len_before != len(app_state["availability"]),
        "state": _state(slot_id=selected_slot_id),
    }
