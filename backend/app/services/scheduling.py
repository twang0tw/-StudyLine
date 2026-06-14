"""Scheduling-related business logic.

Start small here. This module is where helpers from `server.js` should move
once they stop being route-local logic.
"""

from datetime import datetime, timedelta


MIN_WAIT_MINUTES = 3
DEFAULT_AVERAGE_HELP_MINUTES = 7
DEFAULT_TA_COUNT = 1


def slot_id_for(date: str, start_time: str) -> str:
    """Return the stable slot id format used by the current frontend/backend.

    JS version from `server.js`:
        slot-${date}-${startTime.replace(":", "")}

    Example:
        >>> slot_id_for("2026-05-26", "11:30")
        'slot-2026-05-26-1130'
    """

    normalized_time = start_time.replace(":", "")
    return f"slot-{date}-{normalized_time}"

def create_slot(
    date: str,
    start_time: str,
    ta_name: str = "TA",
    location: str = "Office Hours Room",
) -> dict[str, str]:
    """Create one 30-minute office-hours slot."""

    start = datetime.fromisoformat(f"{date}T{start_time}:00")
    end = start + timedelta(minutes=30)

    start_time_str = start.strftime("%H:%M")
    end_time_str = end.strftime("%H:%M")
    return {
        "id": slot_id_for(date, start_time_str),
        "date": date,
        "startTime": start_time_str,
        "endTime": end_time_str,
        "taName": ta_name,
        "location": location,
    }


def create_thirty_minute_slots(
    date: str,
    start_time: str,
    end_time: str,
    ta_name: str = "TA",
    location: str = "Office Hours Room",
) -> list[dict[str, str]]:
    """Expand one availability block into 30-minute slots."""

    slots = []
    cursor = datetime.fromisoformat(f"{date}T{start_time}:00")
    end = datetime.fromisoformat(f"{date}T{end_time}:00")

    while cursor < end:
        slot_start = cursor.strftime("%H:%M")
        slots.append(create_slot(date, slot_start, ta_name, location))
        cursor += timedelta(minutes=30)

    return slots

def format_time(t):
    return t.strftime("%H:%M")

def format_slot(slot):
    return f"{format_time(slot.startTime)} - {format_time(slot.endTime)}"

def get_entry_help_minutes(
    entry: dict,
    average_help_minutes: int = DEFAULT_AVERAGE_HELP_MINUTES,
) -> int:
    """Return an entry's help estimate, falling back to caller-provided context.

    In `server.js`, this function reached into global state:
        entry?.ai?.estimatedHelpMinutes || state.averageHelpMinutes

    In Python, avoid that hidden dependency. The route/repository/service that
    already knows the current average should pass it in explicitly.
    """

    ai = entry.get("ai") or {}
    estimate = ai.get("estimatedHelpMinutes")
    return int(estimate or average_help_minutes)


def estimate_wait(
    entries: list[dict],
    tas_active: int = DEFAULT_TA_COUNT,
    average_help_minutes: int = DEFAULT_AVERAGE_HELP_MINUTES,
) -> int:
    """Estimate total wait for a queue slice.

    All state that used to come from `state` is now passed in. Later, these
    values should come from your database/repository layer.
    """

    safe_ta_count = max(1, tas_active)
    total_time = sum(
        get_entry_help_minutes(entry, average_help_minutes=average_help_minutes)
        for entry in entries
    )
    return max(MIN_WAIT_MINUTES, round(total_time / safe_ta_count))


def crowd_level(wait_time: int) -> str:
    if wait_time <= 10:
        return "low"
    if wait_time <= 22:
        return "medium"
    return "high"

def get_selected_slot_id(student_id, requested_slot_id, first_slot_id, entries):
    student_entry = next((entry for entry in entries if entry.id == student_id), None)
    if requested_slot_id:
        return requested_slot_id
    elif student_entry is not None:
        return student_entry.slotId
    else:
        return first_slot_id