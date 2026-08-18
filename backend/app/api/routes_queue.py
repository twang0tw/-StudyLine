from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services import ai_service
from app.services.db_service import app_state
from app.services.state_service import build_state

router = APIRouter(tags=["queue"])


class AttachmentPayload(BaseModel):
    name: str = Field(default="Attached file", max_length=120)
    type: str = Field(default="unknown", max_length=80)
    size: int = 0
    contentBase64: Optional[str] = None


class CreateQueueEntryRequest(BaseModel):
    name: str = Field(default="Student", max_length=80)
    course: str = Field(default="General", max_length=80)
    need: str = Field(default="Office hours help", max_length=240)
    message: str = Field(default="", max_length=1200)
    slot_id: str
    attachment: Optional[AttachmentPayload] = None


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


def _find_entry(entry_id: str):
    for entry in app_state["queue"]:
        if entry["id"] == entry_id:
            return entry
    for entry in app_state["currentBySlot"].values():
        if entry and entry["id"] == entry_id:
            return entry
    return None


def _session_token_for(entry_id: str) -> str:
    return f"session-{entry_id}"


@router.post("/api/queue", status_code=status.HTTP_201_CREATED)
def create_queue_entry(payload: CreateQueueEntryRequest):
    selected_slot = next(
        (slot for slot in app_state["availability"] if slot["id"] == payload.slot_id),
        None,
    )
    if not selected_slot:
        raise HTTPException(status_code=400, detail="Choose an available office-hour time slot before joining.")

    file = None
    if payload.attachment:
        file = {
            "name": payload.attachment.name.strip()[:120] or "Attached file",
            "type": payload.attachment.type.strip()[:80] or "unknown",
            "size": int(payload.attachment.size or 0),
        }

    message = payload.message.strip()[:1200]
    ai = ai_service.analyze_question(
        course=payload.course,
        need=payload.need,
        message=message,
        file=file,
    )
    entry = {
        "id": str(uuid4()),
        "slotId": payload.slot_id,
        "name": payload.name.strip()[:80] or "Student",
        "course": payload.course.strip()[:80] or "General",
        "need": payload.need.strip()[:120] or "Office hours help",
        "message": message,
        "file": file,
        "ai": ai,
        "status": "waiting",
        "joinedAt": datetime.now(timezone.utc).isoformat(),
    }
    app_state["queue"].append(entry)
    app_state["studentSessions"].setdefault(_session_token_for(entry["id"]), []).insert(0, entry)

    return {
        "entry": entry,
        "queueToken": entry["id"],
        "sessionToken": _session_token_for(entry["id"]),
        "state": _state(student_id=entry["id"], slot_id=payload.slot_id),
    }


@router.get("/api/queue/me")
def queue_me(
    slot_id: Optional[str] = Query(default=None),
    queue_token: Optional[str] = Header(default=None, alias="X-Queue-Token"),
):
    if not queue_token:
        return {"status": "not_joined", "position": None, "personal_wait_minutes": None, "entry_id": None}

    state = _state(student_id=queue_token, slot_id=slot_id)
    return {
        "status": state["queue"]["status"],
        "position": state["queue"]["position"],
        "personal_wait_minutes": state["queue"]["personalWaitMinutes"],
        "entry_id": queue_token,
        "slot_id": state["selectedSlotId"],
    }


@router.delete("/api/queue/me", status_code=status.HTTP_200_OK)
def delete_queue_me(
    slot_id: Optional[str] = Query(default=None),
    queue_token: Optional[str] = Header(default=None, alias="X-Queue-Token"),
):
    if not queue_token:
        return {"removed": False, "state": _state(slot_id=slot_id)}

    before_len = len(app_state["queue"])
    app_state["queue"] = [
        entry for entry in app_state["queue"] if entry["id"] != queue_token
    ]
    for slot, current in list(app_state["currentBySlot"].items()):
        if current and current["id"] == queue_token:
            app_state["currentBySlot"][slot] = None

    return {
        "removed": before_len != len(app_state["queue"]),
        "state": _state(slot_id=slot_id),
    }


@router.delete("/api/queue/{entry_id}", status_code=status.HTTP_200_OK)
def delete_queue_entry(entry_id: str, slot_id: Optional[str] = Query(default=None)):
    before_len = len(app_state["queue"])
    app_state["queue"] = [
        entry for entry in app_state["queue"] if entry["id"] != entry_id
    ]
    return {
        "removed": before_len != len(app_state["queue"]),
        "state": _state(slot_id=slot_id),
    }


@router.get("/api/student/sessions")
def student_sessions(session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    sessions = app_state["studentSessions"].get(session_token or "", [])
    normalized = []
    for entry in sessions:
        slot = next((item for item in app_state["availability"] if item["id"] == entry["slotId"]), {})
        normalized.append(
            {
                **entry,
                "slotId": entry["slotId"],
                "date": slot.get("date"),
                "startTime": slot.get("startTime"),
                "endTime": slot.get("endTime"),
                "waitMinutes": entry.get("ai", {}).get("estimatedHelpMinutes"),
            }
        )
    return {"sessions": normalized}


