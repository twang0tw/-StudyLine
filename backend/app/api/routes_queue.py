from fastapi import APIRouter, HTTPException
from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from app.services.db_service import app_state
import app.services.ai_service
router = APIRouter(prefix="/api/queue", tags=["queue"])

class CreateQueueEntryRequest(BaseModel):
    slot_id: str = Field(default = "", max_length=64)
    selected_slot: str = Field(default = "", max_length=64)



@router.post("entry", status_code=status.HTTP_201_CREATED)
def create_queue_entry(payload: CreateQueueEntryRequest):
    slot_id = payload.slot_id.strip()
    selected_slot = next((slot for slot in app_state["availability"] if slot["id"] == slot_id), None)

    if not selected_slot:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose an available office-hour time slot before joining.")

    file =
    ai = ai_service.analyze_question({

    })