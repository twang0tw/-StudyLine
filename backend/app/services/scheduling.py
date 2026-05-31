from datetime import datetime, timedelta

"""Scheduling-related business logic.

Start small here. This module is where helpers from `server.js` should move
once they stop being route-local logic.
"""


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

# function createSlot({ date, startTime, taName = "Bobby", location = "Office Hours Room" }) {
#     const start = new Date(`${date}T${startTime}:00`);
#     const end = new Date(start.getTime() + 30 * 60 * 1000);
#     const endTime = end.toTimeString().slice(0, 5);
#
#     return {
#     id: slotIdFor(date, startTime),
#     date,
#     startTime,
#     endTime,
#     taName,
#     location,
#     };
# }

def create_slot(date, start_time, ta_name="Bobby", location="Office Hours Room"):
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
        "location": location
    }

# function createThirtyMinuteSlots({ date, startTime, endTime, taName, location }) {
#   const slots = [];
#   let cursor = new Date(`${date}T${startTime}:00`);
#   const end = new Date(`${date}T${endTime}:00`);
#
#   while (cursor < end) {
#     const slotStart = cursor.toTimeString().slice(0, 5);
#     slots.push(createSlot({ date, startTime: slotStart, taName, location }));
#     cursor = new Date(cursor.getTime() + 30 * 60 * 1000);
#   }
#
#   return slots;
# }

def createThirtyMinutesSlots(date, start_time, end_time, ta_name="TA", location="Office Hours Room"):
    slots = []
    i = datetime.fromisoformat(f"{date}T{start_time}:00")
    end = datetime.fromisoformat(f"{date}T{end_time}:00")

    while i < end:
        slot_start = i.strftime("%H:%M")
        slots.append(create_slot(date, slot_start, ta_name, location))
        i += timedelta(minutes=30)

    return slots

# function getEntryHelpMinutes(entry) {
#   return entry?.ai?.estimatedHelpMinutes || state.averageHelpMinutes;
# }
#

# function estimateWait(entries = state.queue) {
#   const totalHelpMinutes = entries.reduce((total, entry) => total + getEntryHelpMinutes(entry), 0);
#   return Math.max(3, Math.round(totalHelpMinutes / state.tasActive));
# }
#

def estimate_wait(entries):
    total_time = entries.reduce

def crowd_level(wait_time):
    if wait_time <= 10:
        return "low"
    elif wait_time <= 30:
        return "medium"
    else:
        return "high"

# function crowdForWait(wait) {
#   if (wait <= 10) return "low";
#   if (wait <= 22) return "medium";
#   return "high";
# }