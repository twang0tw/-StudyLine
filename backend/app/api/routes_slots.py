from fastapi import APIRouter

router = APIRouter(prefix="api/slots", tags=["slots"])

@router.get("")
def get_slots():
    return {"slots":[]}

@router.get("/{slot_id}/overview")
def get_slot_overview(slot_id: str):
    return {
        "slot_id": slot_id,
        "studentsWaiting": 0,
        "tasActive": 1,
        "averageHelpMinutes": 7,
        "estimatedWaitMinutes": 3,
    }
