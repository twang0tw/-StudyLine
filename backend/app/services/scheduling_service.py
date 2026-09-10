"""Scheduling and wait-time domain helpers."""

from datetime import datetime, timedelta
from typing import Any


MIN_WAIT_MINUTES = 3
DEFAULT_AVERAGE_HELP_MINUTES = 7
DEFAULT_TA_COUNT = 1


def slot_id_for(date: str, start_time: str) -> str:
    return f"slot-{date}-{start_time.replace(':', '')}"


def create_slot(
    date: str,
    start_time: str,
    ta_name: str = "TA",
    location: str = "Office Hours Room",
    course_id: str | None = None,
    course_code: str | None = None,
) -> dict[str, Any]:
    start = datetime.fromisoformat(f"{date}T{start_time}:00")
    end = start + timedelta(minutes=30)
    return {
        "id": slot_id_for(date, start.strftime("%H:%M")),
        "courseId": course_id,
        "courseCode": course_code,
        "date": date,
        "startTime": start.strftime("%H:%M"),
        "endTime": end.strftime("%H:%M"),
        "taName": ta_name,
        "location": location,
        "zoomLink": "",
        "status": "scheduled",
        "changeHighlighted": False,
        "changeNotice": "",
    }


def create_thirty_minute_slots(
    date: str,
    start_time: str,
    end_time: str,
    ta_name: str = "TA",
    location: str = "Office Hours Room",
    course_id: str | None = None,
    course_code: str | None = None,
) -> list[dict[str, Any]]:
    slots = []
    cursor = datetime.fromisoformat(f"{date}T{start_time}:00")
    end = datetime.fromisoformat(f"{date}T{end_time}:00")

    while cursor < end:
        slots.append(
            create_slot(
                date=date,
                start_time=cursor.strftime("%H:%M"),
                ta_name=ta_name,
                location=location,
                course_id=course_id,
                course_code=course_code,
            )
        )
        cursor += timedelta(minutes=30)

    return slots


def get_entry_help_minutes(
    entry: dict[str, Any],
    average_help_minutes: int = DEFAULT_AVERAGE_HELP_MINUTES,
) -> int:
    ai = entry.get("ai") or {}
    return int(ai.get("estimatedHelpMinutes") or average_help_minutes)


def estimate_wait(
    entries: list[dict[str, Any]],
    tas_active: int = DEFAULT_TA_COUNT,
    average_help_minutes: int = DEFAULT_AVERAGE_HELP_MINUTES,
) -> int:
    if not entries:
        return 0
    safe_ta_count = max(1, int(tas_active or DEFAULT_TA_COUNT))
    total_time = sum(get_entry_help_minutes(entry, average_help_minutes) for entry in entries)
    return max(MIN_WAIT_MINUTES, round(total_time / safe_ta_count))


def crowd_level(wait_time: int) -> str:
    if wait_time <= 10:
        return "low"
    if wait_time <= 22:
        return "medium"
    return "high"
