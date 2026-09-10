from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services import db_service
from app.services.scheduling_service import crowd_level, estimate_wait
from app.services.state_service import build_state


router = APIRouter(tags=["slots"])


class CreateAvailabilityRequest(BaseModel):
    course_id: str | None = Field(default=None, alias="courseId")
    title: str = Field(default="", max_length=120)
    date: str
    start_time: str = Field(default="09:00", alias="startTime")
    end_time: str = Field(default="09:30", alias="endTime")
    location: str = Field(default="Office Hours Room", max_length=160)
    zoom_link: str = Field(default="", alias="zoomLink", max_length=240)

    class Config:
        allow_population_by_field_name = True


@router.get("/api/slots")
def list_slots(course_id: Optional[str] = Query(default=None, alias="courseId")):
    snapshot = db_service.get_app_snapshot(course_id=course_id)
    state = build_state(
        slots=snapshot["slots"],
        availability=snapshot["availability"],
        queue_entries=snapshot["queue"],
        current_by_slot=snapshot["currentBySlot"],
        served_by_slot=snapshot["servedBySlot"],
        tas_active=snapshot["tasActive"],
        avg_help_minutes=snapshot["averageHelpMinutes"],
        forecast=[],
    )
    return db_service.serialize({"slots": state["slots"]})


@router.get("/api/slots/{slot_id}/overview")
def slot_overview(slot_id: str):
    waiting = db_service.list_waiting_entries(slot_id)
    section = db_service.find_slot(slot_id)
    settings = db_service.get_settings()
    if section and "participantTaIds" in section:
        ta_count = len(section.get("participantTaIds") or [])
    elif section:
        ta_count = len(section.get("taIds") or [])
    else:
        ta_count = settings["tasActive"]
    wait = estimate_wait(waiting, ta_count, settings["averageHelpMinutes"])
    return {
        "students_waiting": len(waiting),
        "tas_active": ta_count,
        "average_help_minutes": settings["averageHelpMinutes"],
        "estimated_wait_minutes": wait,
        "crowd": crowd_level(wait),
    }


@router.post("/api/availability", status_code=status.HTTP_201_CREATED)
def create_availability(
    payload: CreateAvailabilityRequest,
    x_user_token: str | None = Header(default=None, alias="X-User-Token"),
):
    user = db_service.user_for_token(x_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in.")
    if not payload.course_id:
        raise HTTPException(status_code=400, detail="courseId is required")
    section = db_service.create_section(
        user=user,
        course_id=payload.course_id,
        date_value=payload.date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=payload.location,
        zoom_link=payload.zoom_link,
        title=payload.title,
    )
    return {"slots": [db_service.serialize(section)], "section": db_service.serialize(section)}


@router.delete("/api/availability/{slot_id}", status_code=status.HTTP_200_OK)
def delete_availability(
    slot_id: str,
    x_user_token: str | None = Header(default=None, alias="X-User-Token"),
):
    if not db_service.user_for_token(x_user_token):
        raise HTTPException(status_code=401, detail="Please sign in.")
    return {"removed": db_service.delete_slot(slot_id)}
