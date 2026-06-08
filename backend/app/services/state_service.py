import scheduling
from backend.app.services.scheduling import estimate_wait


def build_state(
        slots,
        queue_entries,
        current_by_slot,
        served_by_slot,
        student_id=None,
        requested_slot_id=None,
        tas_active=1,
        avg_help_minutes=7
):
    selected_slot_id = scheduling.get_selected_slot_id(student_id, requested_slot_id, slots[0].id, queue_entries)
    wait_queue = (entry for entry in queue_entries if entry.status == "waiting" and entry.slotId == selected_slot_id)
    wait_time = estimate_wait(wait_queue, tas_active, avg_help_minutes)
    position = next((i for i, entry in enumerate(wait_queue) if entry.id == student_id), -1) + 1 if student_id else 0
    current_student = current_by_slot[selected_slot_id] if selected_slot_id else None
    is_current_student = student_id and current_student and current_student.id == student_id
    personal_entries = wait_queue[:position] if position > 0 else []

    return {
        slots,
        selected_slot_id,
        live {
            students_waiting: len(wait_queue),
            tas_active: tas_active,
            avg_help_minutes: avg_help_minutes,
            estimate_wait: estimate_wait,
            crowd: scheduling.crowd_level(wait_time)
        },
        queue {
            student_id = student_id if student_id else None,
            position = position if position > 0 else None,
            personal_wait_minutes = estimate_wait(wait_queue, tas_active, avg_help_minutes) if position > 0 else None,
            status = "called" if is_current_student, "next" elif position == 1, "waiting" elif position > 1 else "not_joined"
        }

    }