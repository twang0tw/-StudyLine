from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.services import ai_service
from app.services.db_service import app_state
router = APIRouter(prefix="/api/queue", tags=["queue"])

class AttachmentPayload(BaseModel):
    name: str = Field(default="Attached file", max_length=120)
    type: str = Field(default="unknown")
    size: int = 0
    contentBase64: str | None = None

class CreateQueueEntryRequest(BaseModel):
    name: str = Field(default="Student", max_length=80)
    course: str = Field(default="General", max_length=80)
    need: str = Field(default="Office hours help", max_length=240)
    message: str = Field(default="", max_length=1200)
    slot_id: str
    attachment: AttachmentPayload | None = None


@router.post("entry", status_code=status.HTTP_201_CREATED)
def create_queue_entry(payload: CreateQueueEntryRequest):
    file = None

    if payload.attachment:
        file = {
            "name": payload.attachment.name.strip()[:120] or "Attached file",
            "type": payload.attachment.type.strip()[:80] or "unknown",
            "size": int(payload.attachmen.size or 0),
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
        "need": payload.need.strip()[:80] or "Office hours help",
        "message": message,
        "file": file,
        "ai": ai,
        "status": "waiting",
        "joinedAt": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "entry": entry,
        "queueToken": entry["id"],
    }