from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.services.db_service import app_state
from app.services.state_service import build_state

router = APIRouter(tags=["staff"])


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


def _selected_slot_id(slot_id: Optional[str]) -> Optional[str]:
    if slot_id:
        return slot_id
    return app_state["availability"][0]["id"] if app_state["availability"] else None


def _find_entry(entry_id: str):
    for entry in app_state["queue"]:
        if entry["id"] == entry_id:
            return entry
    for entry in app_state["currentBySlot"].values():
        if entry and entry["id"] == entry_id:
            return entry
    return None


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
    entry = _find_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found.")
    return entry


@router.post("/api/staff/call-next", status_code=status.HTTP_200_OK)
def call_next(slot_id: Optional[str] = Query(default=None)):
    selected_slot_id = _selected_slot_id(slot_id)
    if not selected_slot_id:
        return {"next": None, "state": _state()}

    current = app_state["currentBySlot"].get(selected_slot_id)
    if current:
        app_state["servedBySlot"][selected_slot_id] = app_state["servedBySlot"].get(selected_slot_id, 0) + 1

    next_index = next(
        (
            index
            for index, entry in enumerate(app_state["queue"])
            if entry["status"] == "waiting" and entry["slotId"] == selected_slot_id
        ),
        None,
    )
    next_entry = app_state["queue"].pop(next_index) if next_index is not None else None

    if next_entry:
        next_entry["status"] = "called"
        next_entry["calledAt"] = datetime.now(timezone.utc).isoformat()

    app_state["currentBySlot"][selected_slot_id] = next_entry
    return {"next": next_entry, "state": _state(slot_id=selected_slot_id)}


@router.post("/api/staff/serve-current", status_code=status.HTTP_200_OK)
def serve_current(slot_id: Optional[str] = Query(default=None)):
    selected_slot_id = _selected_slot_id(slot_id)
    served = app_state["currentBySlot"].get(selected_slot_id) if selected_slot_id else None

    if served and selected_slot_id:
        app_state["servedBySlot"][selected_slot_id] = app_state["servedBySlot"].get(selected_slot_id, 0) + 1
        app_state["currentBySlot"][selected_slot_id] = None

    return {"served": served, "state": _state(slot_id=selected_slot_id)}
