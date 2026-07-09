from fastapi import APIRouter
from services import queue_service

router = APIRouter(prefix="api/queue", tags=["queue"])

@router.post("")
def join_queue():
    return queue_service.join_queue()

@router.get("/{queue")\
