from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.services import db_service
from app.services.state_service import build_state

router = APIRouter(tags=["staff"])


def _state(student_id: Optional[str] = None, slot_id: Optional[str] = None):
    snapshot = db_service.get_app_snapshot()
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


def _selected_slot_id(slot_id: Optional[str]) -> Optional[str]:
    if slot_id:
        return slot_id
    slots = db_service.list_slots()
    return slots[0]["id"] if slots else None


@router.get("/api/staff/queue")
def staff_queue(slot_id: Optional[str] = Query(default=None)):
    selected_slot_id = _selected_slot_id(slot_id)
    state = _state(slot_id=selected_slot_id)
    return {
        "served_count": state["staff"]["servedCount"],
        "current_student_id": state["staff"]["currentStudent"]["id"] if state["staff"]["currentStudent"] else None,
        "waiting_entries": [
            {
                "id": entry["id"],
                "name": entry.get("name", "Student"),
                "course": entry.get("course", "General"),
                "need": entry.get("need", "Office hours help"),
                "position": entry["position"],
                "estimated_help_minutes": entry.get("ai", {}).get("estimatedHelpMinutes", 0),
            }
            for entry in state["staff"]["waitingEntries"]
        ],
    }


@router.get("/api/staff/queue/{entry_id}")
def staff_queue_entry(entry_id: str):
    entry = db_service.find_queue_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found.")
    return entry


@router.post("/api/staff/call-next", status_code=status.HTTP_200_OK)
def call_next(slot_id: Optional[str] = Query(default=None)):
    selected_slot_id = _selected_slot_id(slot_id)
    if not selected_slot_id:
        return {"next": None, "state": _state()}

    current = db_service.get_current_student(selected_slot_id)
    if current:
        db_service.increment_served_count(selected_slot_id)

    next_entry = db_service.pop_next_waiting_entry(selected_slot_id)
    if next_entry:
        next_entry["status"] = "called"
        next_entry["calledAt"] = datetime.now(timezone.utc)

    db_service.set_current_student(selected_slot_id, next_entry)
    return {"next": next_entry, "state": _state(slot_id=selected_slot_id)}


@router.post("/api/staff/serve-current", status_code=status.HTTP_200_OK)
def serve_current(slot_id: Optional[str] = Query(default=None)):
    selected_slot_id = _selected_slot_id(slot_id)
    served = db_service.get_current_student(selected_slot_id) if selected_slot_id else None

    if served and selected_slot_id:
        db_service.increment_served_count(selected_slot_id)
        db_service.clear_current_student(selected_slot_id)

    return {"served": served, "state": _state(slot_id=selected_slot_id)}
