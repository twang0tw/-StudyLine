"""Read-model helpers that shape data for the browser UI."""

from datetime import time
from typing import Any

from app.services.scheduling_service import crowd_level, estimate_wait


def build_state(
    slots,
    queue_entries,
    current_by_slot,
    served_by_slot,
    availability=None,
    student_id=None,
    requested_slot_id=None,
    tas_active=1,
    avg_help_minutes=7,
    forecast=None,
):
    slots = list(slots or [])
    availability = list(availability or slots)
    queue_entries = list(queue_entries or [])
    current_by_slot = current_by_slot or {}
    served_by_slot = served_by_slot or {}
    selected_slot_id = _selected_slot_id(student_id, requested_slot_id, slots, queue_entries, current_by_slot)
    waiting = [
        entry
        for entry in queue_entries
        if entry.get("status") == "waiting" and entry.get("slotId") == selected_slot_id
    ]
    position = _position_for_student(waiting, student_id)
    current_student = current_by_slot.get(selected_slot_id) if selected_slot_id else None
    is_current_student = bool(student_id and current_student and current_student.get("id") == student_id)
    selected_slot = next((slot for slot in slots if slot.get("id") == selected_slot_id), None)
    section_ta_count = _section_ta_count(selected_slot, tas_active)
    wait_time = estimate_wait(waiting, section_ta_count, avg_help_minutes)

    return {
        "slots": [_slot_state(slot, queue_entries, tas_active, avg_help_minutes) for slot in slots],
        "selectedSlotId": selected_slot_id,
        "live": {
            "studentsWaiting": len(waiting),
            "tasActive": section_ta_count,
            "averageHelpMinutes": avg_help_minutes,
            "estimatedWaitMinutes": wait_time,
            "crowd": crowd_level(wait_time),
        },
        "queue": {
            "studentId": student_id or None,
            "position": position if position > 0 else None,
            "personalWaitMinutes": estimate_wait(waiting[:position], section_ta_count, avg_help_minutes) if position > 0 else None,
            "status": "called" if is_current_student else "next" if position == 1 else "waiting" if position > 1 else "not_joined",
        },
        "staff": {
            "currentStudent": current_student,
            "waitingEntries": [
                {
                    **entry,
                    "position": index + 1,
                    "estimatedWaitMinutes": estimate_wait(waiting[: index + 1], section_ta_count, avg_help_minutes),
                }
                for index, entry in enumerate(waiting)
            ],
            "servedCount": int(served_by_slot.get(selected_slot_id, 0)) if selected_slot_id else 0,
        },
        "sessions": [
            {
                "id": slot.get("id"),
                "time": _format_slot(slot),
                "room": slot.get("location"),
                "wait": _slot_wait(slot, queue_entries, tas_active, avg_help_minutes),
                "crowd": crowd_level(_slot_wait(slot, queue_entries, tas_active, avg_help_minutes)),
                "note": f"{slot.get('courseCode') or 'Course'} with {slot.get('taName') or 'TA'}",
            }
            for slot in availability
        ],
        "forecast": list(forecast or []),
    }


def _selected_slot_id(student_id, requested_slot_id, slots, queue_entries, current_by_slot):
    if requested_slot_id:
        return requested_slot_id

    if student_id:
        student_entry = next((entry for entry in queue_entries if entry.get("id") == student_id), None)
        if student_entry:
            return student_entry.get("slotId")
        current_entry = next((entry for entry in current_by_slot.values() if entry and entry.get("id") == student_id), None)
        if current_entry:
            return current_entry.get("slotId")

    return slots[0].get("id") if slots else None


def _slot_state(slot, queue_entries, tas_active, avg_help_minutes):
    waiting = [entry for entry in queue_entries if entry.get("status") == "waiting" and entry.get("slotId") == slot.get("id")]
    wait = estimate_wait(waiting, _section_ta_count(slot, tas_active), avg_help_minutes)
    return {
        **slot,
        "label": _format_slot(slot),
        "studentsWaiting": len(waiting),
        "estimatedWaitMinutes": wait,
        "crowd": crowd_level(wait),
    }


def _slot_wait(slot, queue_entries, tas_active, avg_help_minutes):
    waiting = [entry for entry in queue_entries if entry.get("status") == "waiting" and entry.get("slotId") == slot.get("id")]
    return estimate_wait(waiting, _section_ta_count(slot, tas_active), avg_help_minutes)


def _section_ta_count(slot, fallback):
    if slot and "participantTaIds" in slot:
        return len(slot.get("participantTaIds") or [])
    if slot and "taIds" in slot:
        return len(slot.get("taIds") or [])
    return max(1, int(fallback or 1))


def _position_for_student(waiting, student_id):
    if not student_id:
        return 0
    for index, entry in enumerate(waiting):
        if entry.get("id") == student_id:
            return index + 1
    return 0


def _format_slot(slot):
    return f"{_format_time(slot.get('startTime'))} - {_format_time(slot.get('endTime'))}"


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
