from random import random, randrange
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Query

from app.services import db_service, state_service

router = APIRouter(tags=["state"])


async def _selected_slot_id(slot_id: Optional[str]) -> Optional[str]:
    if slot_id:
        return slot_id
    slots = await db_service.list_slots()
    return slots[0]["id"] if slots else None


@router.get("/api/state")
async def get_state(
    student_id: Optional[str] = Query(default=None, alias="studentId"),
    slot_id: Optional[str] = Query(default=None, alias="slotId"),
):
    snapshot = await db_service.get_app_snapshot()
    return state_service.build_state(
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


@router.post("/api/simulate-crowd")
async def simulate_crowd(
    slot_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None, alias="studentId"),
):
    selected_slot_id = await _selected_slot_id(slot_id)
    await db_service.update_settings(
        {
            "tasActive": 3 if random() > 0.78 else 2,
            "averageHelpMinutes": 6 + randrange(4),
        }
    )

    if selected_slot_id and random() > 0.5:
        await db_service.insert_queue_entry(
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
                "joinedAt": datetime.now(timezone.utc),
            }
        )
    elif selected_slot_id:
        await db_service.delete_first_waiting_entry(selected_slot_id)

    return await get_state(student_id=student_id, slot_id=selected_slot_id)
