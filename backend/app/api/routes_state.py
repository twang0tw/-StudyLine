from typing import Optional

from fastapi import APIRouter, Query

from app.services import db_service, state_service


router = APIRouter(tags=["state"])


@router.get("/api/state")
def get_state(
    student_id: Optional[str] = Query(default=None, alias="studentId"),
    slot_id: Optional[str] = Query(default=None, alias="slotId"),
):
    snapshot = db_service.get_app_snapshot()
    return db_service.serialize(
        state_service.build_state(
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
    )
