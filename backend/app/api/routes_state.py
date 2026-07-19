from fastapi import APIRouter, Query

from app.services import state_service
from app.services.db_service import app_state

router = APIRouter(prefix="api/state", tags=["state"])

@router.get("")
def get_state(
    student_id: str | None = Query(default=None, alias="studentId"),
    slot_id: str | None = Query(default=None, alias="slotId"),
):
    return state_service.build_state(
        slots = app_state["availability"],
        availability = app_state["availability"],
        queue_entries = app_state["queue"],
        current_by_slot = app_state["currentBySlot"],
        served_by_slot = app_state["servedBySlot"],
        student_id = student_id,
        requested_slot_id = slot_id,
        tas_active = app_state["tasActive"],
        avg_help_minutes = app_state["averageHelpMinutes"],
        forecast = app_state["forecast"],
    )
