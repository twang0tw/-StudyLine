from typing import Optional

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.services import db_service
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


async def _state(student_id: Optional[str] = None, slot_id: Optional[str] = None):
    snapshot = await db_service.get_app_snapshot()
    return build_state(
        slots=snapshot["slots"],
        availability=snapshot["availability"],
        queue_entries=snapshot["queue"],
        current_by_slot=snapshot["currentBySlot"],
        served_by_slot=snapshot["servedBySlot"],
        student_id=student_id,
        requested_slot_id=slot_id,
        tas_active=snapshot["tasActive"],
        avg_help_minutes=snapshot["averageHelpMinutes"],
        forecast=snapshot["forecast"],
    )


@router.get("/api/slots")
async def list_slots():
    state = await _state()
    return {"slots": state["slots"]}


@router.get("/api/slots/{slot_id}/overview")
async def slot_overview(slot_id: str):
    waiting = await db_service.list_waiting_entries(slot_id)
    settings = await db_service.get_settings()
    wait = estimate_wait(
        waiting,
        tas_active=settings["tasActive"],
        average_help_minutes=settings["averageHelpMinutes"],
    )
    return {
        "students_waiting": len(waiting),
        "tas_active": settings["tasActive"],
        "average_help_minutes": settings["averageHelpMinutes"],
        "estimated_wait_minutes": wait,
        "crowd": crowd_level(wait),
    }


@router.get("/api/forecast")
async def forecast(slot_id: Optional[str] = None):
    return {"forecast": await db_service.list_forecast()}


@router.post("/api/availability", status_code=status.HTTP_201_CREATED)
async def create_availability(payload: CreateAvailabilityRequest):
    slots = create_thirty_minute_slots(
        date=payload.date[:10],
        start_time=payload.start_time[:5],
        end_time=payload.end_time[:5],
        ta_name=payload.ta_name.strip()[:80] or "TA",
        location=payload.location.strip()[:100] or "Office Hours Room",
    )
    inserted_slots = await db_service.insert_slots(slots)
    selected_slot_id = slots[0]["id"] if slots else None

    return {"slots": inserted_slots, "state": await _state(slot_id=selected_slot_id)}


@router.delete("/api/availability/{slot_id}", status_code=status.HTTP_200_OK)
async def delete_availability(slot_id: str):
    removed = await db_service.delete_slot(slot_id)
    slots = await db_service.list_slots()
    selected_slot_id = slots[0]["id"] if slots else None
    return {
        "removed": removed,
        "state": await _state(slot_id=selected_slot_id),
    }
