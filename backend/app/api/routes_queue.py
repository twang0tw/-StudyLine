from fastapi import APIRouter

router = APIRouter(prefix="/api/queue", tags=["queue"])


@router.post("")
def join_queue():
    return {"message": "queue route not implemented yet"}


@router.get("/me")
def get_my_queue_status(slot_id: str | None = None):
    return {
        "slotId": slot_id,
        "status": "not_joined",
        "position": None,
        "personalWaitMinutes": None,
    }


@router.delete("/me")
def leave_queue(slot_id: str | None = None):
    return {"removed": False, "slotId": slot_id}