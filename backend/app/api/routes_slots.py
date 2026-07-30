from datetime import date as DataType

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.services import scheduling_service, state_service
from app.services.db_service import app_state
from app.services.state_service import build_state

router = APIRouter(prefix="api/slots", tags=["slots"])

class CreateAvailabilityRequest(BaseModel):
    date: str
    startTime: str = Field(default="09:00", max_length=5)
    endTime: str = Field(default="09:30", max_length=5)
    taName: str = Field(default="TA", max_length=80)
    location: str = Field(default="Office Hours Room", max_length=100)

# from js 'handleCreateAvailabilityRoute' function
@router.post("/availability", status_code=status.HTTP_201_CREATED)
def create_availability(payload: CreateAvailabilityRequest):
    slots = scheduling_service.create_thirty_minutes_slots(
        date = payload.date[:10],
        startTime = payload.startTime[:5],
        endTime = payload.endTime[:5],
        ta_name = payload.taName.strip(),
        location = payload.location.strip(),
    )

    existing_slot_ids = {slot["id"] for slot in app_state["availability"]["slots"]}

    for slot in slots:
        if slot not in existing_slot_ids:
            app_state["availability"].append(slot)

    app_state["availability"].sort(key=lambda slot: f"{slot['date']}T{slot['startTime']}")

    selected_slot_id = slots[0]["id"] if slots else None

    return {
        "slots": slots,
        "state": state_service.build_state(
            slots = app_state["availability"],
            queue_entries = app_state["queue"],
            current_by_slot = app_state["currentBySlot"],
            served_by_slot = app_state["servedBySlot"],
            avalibility=app_state["availability"],
            student_id = None,
            requested_slot_id = selected_slot_id,
            tas_active = app_state["tasActive"],
            avg_help_minutes = app_state["averageHelpMinutes"],
            forecast = app_state["forecast"],
        ),
    }

# from js 'handleDeleteAvailabilityRoute' function
@router.delete("/availability/{slot_id}", status_code=status.HTTP_200_OK)
def delete_availability(slot_id: str):
    len_before = len(app_state["availability"])

    app_state["availability"] = [
        slot for slot in app_state["availability"]
        if slot["id"] != slot_id
    ]

    app_state["queue"] = [
        entry for entry in app_state["queue"]
        if entry["slotId"] != slot_id
    ]

    app_state["currentBySlot"].pop(slot_id, None)
    app_state["servedBySlot"].pop(slot_id, None)

    selected_slot_id = app_state["availability"][0]["id"] if app_state["availability"] else None

    return {
        "removed": len_before != len(app_state["availability"]),
        "state": state_service.build_state(
            slots=app_state["availability"],
            availability=app_state["availability"],
            queue_entries=app_state["queue"],
            current_by_slot=app_state["currentBySlot"],
            served_by_slot=app_state["servedBySlot"],
            student_id=None,
            requested_slot_id=selected_slot_id,
            tas_active=app_state["tasActive"],
            avg_help_minutes=app_state["averageHelpMinutes"],
            forecast=app_state["forecast"],
        ),
    }