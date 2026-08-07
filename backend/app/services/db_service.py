"""Temporary in-memory storage for the FastAPI migration.

This mirrors the old `state` object in `server.js`. Keep it only while the API
contract is being ported; later this should be replaced by repository/database
calls.
"""

from datetime import date

from app.services.scheduling_service import create_slot, slot_id_for

today = date.today().isoformat()

app_state = {
    "availability": [
        create_slot(today, "11:30", "Bobby", "Library 204"),
        create_slot(today, "13:00", "Bobby", "STEM Center"),
        create_slot(today, "15:30", "Bobby", "Library 204"),
    ],
    "queue": [
        {
            "id": "demo-1",
            "slotId": slot_id_for(today, "11:30"),
            "name": "Maya",
            "course": "CS 101",
            "need": "Debugging help",
            "message": "My loop stops after the first test case.",
            "file": {"name": "lab4.py", "type": "text/x-python", "size": 4200},
            "ai": {
                "summary": "Likely debugging support involving loops or indexing.",
                "estimatedHelpMinutes": 9,
                "confidence": "medium",
                "source": "demo",
            },
            "status": "waiting",
            "joinedAt": "2026-06-24T11:00:00+00:00",
        }
    ],
    "currentBySlot": {},
    "servedBySlot": {},
    "tasActive": 2,
    "averageHelpMinutes": 7,
    "forecast": [
        {"time": "10 AM", "level": 32, "crowd": "low"},
        {"time": "12 PM", "level": 74, "crowd": "high"},
        {"time": "2 PM", "level": 58, "crowd": "medium"},
        {"time": "4 PM", "level": 24, "crowd": "low"},
    ],
    "studentSessions": {},
}

def list_slots():
    return app_state["availability"]

def list_queue_entries():
    return app_state["queue"]

def insert_queue_entry(entry):
    if not entry:
        raise ValueError("entry can't be None")
    app_state["queue"].append(entry)


def get_current_by_slot():
    return app_state["currentBySlot"]

def increment_served_count(slot_id):
