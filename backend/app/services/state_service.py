from dataclasses import asdict, is_dataclass
from datetime import time
from typing import Any

from .scheduling_service import crowd_level, estimate_wait


def build_state(
        slots,
        avalibility,
        queue_entries,
        current_by_slot,
        served_by_slot,
        student_id=None,
        requested_slot_id=None,
        tas_active=1,
        avg_help_minutes=7,
        forecast=None,
):
    slots = list(slots or [])
    availability = list(avalibility or slots)
    queue_entries = list(queue_entries or [])
    current_by_slot = current_by_slot or {}
    served_by_slot = served_by_slot or {}

    selected_slot_id = _get_selected_slot_id(
        student_id=student_id,
        requested_slot_id=requested_slot_id,
        slots=slots,
        queue_entries=queue_entries,
        current_by_slot=current_by_slot,
    )
    waiting = [
        entry
        for entry in queue_entries
        if _get(entry, "status") == "waiting" and _get(entry, "slotId", "slot_id") == selected_slot_id
    ]
    wait_time = _estimate_wait(waiting, tas_active, avg_help_minutes)
    position = _position_for_student(waiting, student_id)
    current_student = _to_dict(_get_from_mapping(current_by_slot, selected_slot_id)) if selected_slot_id else None
    is_current_student = bool(student_id and current_student and _get(current_student, "id") == student_id)
    personal_entries = waiting[:position] if position > 0 else []
    return {
        "slots": [
            _build_slot_state(slot, queue_entries, tas_active, avg_help_minutes)
            for slot in slots
        ],
        "selectedSlotId": selected_slot_id,
        "live": {
            "studentsWaiting": len(waiting),
            "tasActive": tas_active,
            "averageHelpMinutes": avg_help_minutes,
            "estimatedWaitMinutes": wait_time,
            "crowd": crowd_level(wait_time),
        },
        "queue": {
            "studentId": student_id or None,
            "position": position if position > 0 else None,
            "personalWaitMinutes": _estimate_wait(personal_entries, tas_active, avg_help_minutes) if position > 0 else None,
            "status": (
                "called"
                if is_current_student
                else "next"
                if position == 1
                else "waiting"
                if position > 1
                else "not_joined"
            ),
        },
        "staff": {
            "currentStudent": current_student,
            "waitingEntries": [
                {
                    **_to_dict(entry),
                    "position": index + 1,
                    "estimatedWaitMinutes": _estimate_wait(waiting[: index + 1], tas_active, avg_help_minutes),
                }
                for index, entry in enumerate(waiting)
            ],
            "servedCount": _get_from_mapping(served_by_slot, selected_slot_id, 0) if selected_slot_id else 0,
        },
        "sessions": [
            {
                "id": _get(slot, "id"),
                "time": _format_slot(slot),
                "room": _get(slot, "location"),
                "wait": _slot_wait(slot, queue_entries, tas_active, avg_help_minutes),
                "crowd": crowd_level(_slot_wait(slot, queue_entries, tas_active, avg_help_minutes)),
                "note": f"{_get(slot, 'taName', 'ta_name') or 'TA'} available",
            }
            for slot in availability
        ],
        "forecast": list(forecast or []),
    }


def _get(source: Any, *keys: str, default=None):
    for key in keys:
        if isinstance(source, dict) and source.get(key) is not None:
            return source[key]
        if not isinstance(source, dict) and hasattr(source, key):
            value = getattr(source, key)
            if value is not None:
                return value
    return default


def _get_from_mapping(source: Any, key: str | None, default=None):
    if not key:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _to_dict(source: Any):
    if source is None:
        return None
    if isinstance(source, dict):
        return dict(source)
    if is_dataclass(source):
        return asdict(source)
    model_dump = getattr(source, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return dict(vars(source))


def _get_selected_slot_id(student_id, requested_slot_id, slots, queue_entries, current_by_slot):
    if requested_slot_id:
        return requested_slot_id

    student_entry = None
    if student_id:
        student_entry = next((_to_dict(entry) for entry in queue_entries if _get(entry, "id") == student_id), None)
        if student_entry is None:
            student_entry = next(
                (_to_dict(entry) for entry in _mapping_values(current_by_slot) if entry and _get(entry, "id") == student_id),
                None,
            )

    if student_entry:
        return _get(student_entry, "slotId", "slot_id")
    return _get(slots[0], "id") if slots else None


def _mapping_values(source: Any):
    return source.values() if isinstance(source, dict) else vars(source).values()


def _position_for_student(waiting, student_id):
    if not student_id:
        return 0
    for index, entry in enumerate(waiting):
        if _get(entry, "id") == student_id:
            return index + 1
    return 0


def _build_slot_state(slot, queue_entries, tas_active, avg_help_minutes):
    slot_waiting = _waiting_for_slot(slot, queue_entries)
    wait = _estimate_wait(slot_waiting, tas_active, avg_help_minutes)
    return {
        **_to_dict(slot),
        "label": _format_slot(slot),
        "studentsWaiting": len(slot_waiting),
        "estimatedWaitMinutes": wait,
        "crowd": crowd_level(wait),
    }


def _waiting_for_slot(slot, queue_entries):
    slot_id = _get(slot, "id")
    return [
        entry
        for entry in queue_entries
        if _get(entry, "status") == "waiting" and _get(entry, "slotId", "slot_id") == slot_id
    ]


def _slot_wait(slot, queue_entries, tas_active, avg_help_minutes):
    return _estimate_wait(_waiting_for_slot(slot, queue_entries), tas_active, avg_help_minutes)


def _estimate_wait(entries, tas_active, avg_help_minutes):
    return estimate_wait([_to_dict(entry) for entry in entries], tas_active, avg_help_minutes)


def _format_slot(slot):
    start_time = _get(slot, "startTime", "start_time")
    end_time = _get(slot, "endTime", "end_time")
    return f"{_format_time(start_time)} - {_format_time(end_time)}"


def _format_time(value):
    if isinstance(value, time):
        hour = value.hour
        minute = value.minute
    else:
        hour_text, minute_text = str(value or "00:00").split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text[:2])

    suffix = "PM" if hour >= 12 else "AM"
    display_hour = hour % 12 or 12
    return f"{display_hour}:{minute:02d} {suffix}"