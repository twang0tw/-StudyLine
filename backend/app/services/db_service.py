"""MongoDB storage helpers for the FastAPI migration."""

import os
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import MongoClient, ReturnDocument

from app.services.scheduling_service import create_slot, slot_id_for

load_dotenv()

try:
    import certifi
except ImportError:
    certifi = None

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "studyline_dev")
RETENTION_DAYS = int(os.getenv("DB_RETENTION_DAYS", "30"))

client_kwargs = {}
if certifi is not None and MONGO_URL.startswith("mongodb+srv://"):
    client_kwargs["tlsCAFile"] = certifi.where()

client = MongoClient(MONGO_URL, **client_kwargs)
db = client[MONGO_DB_NAME]

slots_collection = db["slots"]
queue_collection = db["queue"]
slot_status_collection = db["slot_status"]
settings_collection = db["settings"]
forecast_collection = db["forecast"]
sessions_collection = db["student_sessions"]

DEFAULT_SETTINGS = {
    "tasActive": 2,
    "averageHelpMinutes": 7,
}

DEFAULT_FORECAST = [
    {"time": "10 AM", "level": 32, "crowd": "low"},
    {"time": "12 PM", "level": 74, "crowd": "high"},
    {"time": "2 PM", "level": 58, "crowd": "medium"},
    {"time": "4 PM", "level": 24, "crowd": "low"},
]


def _without_id(document: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not document:
        return None
    document = dict(document)
    document.pop("_id", None)
    return document


def _default_slots() -> list[dict[str, str]]:
    today = date.today().isoformat()
    return [
        create_slot(today, "11:30", "Bobby", "Library 204"),
        create_slot(today, "13:00", "Bobby", "STEM Center"),
        create_slot(today, "15:30", "Bobby", "Library 204"),
    ]


def initialize_database() -> None:
    slots_collection.create_index("id", unique=True)
    slots_collection.create_index([("date", 1), ("startTime", 1)])
    queue_collection.create_index("id", unique=True)
    queue_collection.create_index([("slotId", 1), ("status", 1), ("joinedAt", 1)])
    queue_collection.create_index("expiresAt", expireAfterSeconds=0)
    slot_status_collection.create_index("slotId", unique=True)
    sessions_collection.create_index([("sessionToken", 1), ("createdAt", -1)])
    sessions_collection.create_index("expiresAt", expireAfterSeconds=0)

    settings_collection.update_one(
        {"_id": "app"},
        {"$setOnInsert": DEFAULT_SETTINGS},
        upsert=True,
    )

    if forecast_collection.count_documents({}) == 0:
        forecast_collection.insert_many(DEFAULT_FORECAST)

    if slots_collection.count_documents({}) == 0:
        insert_slots(_default_slots())


def list_slots() -> list[dict[str, Any]]:
    return list(
        slots_collection.find({}, {"_id": 0}).sort([("date", 1), ("startTime", 1)])
    )


def find_slot(slot_id: str) -> Optional[dict[str, Any]]:
    if not slot_id:
        return None
    return slots_collection.find_one({"id": slot_id}, {"_id": 0})


def insert_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not slots:
        return []

    existing_ids = {
        slot["id"]
        for slot in slots_collection.find(
            {"id": {"$in": [slot["id"] for slot in slots]}},
            {"id": 1, "_id": 0},
        )
    }
    new_slots = [slot for slot in slots if slot["id"] not in existing_ids]

    if new_slots:
        # PyMongo mutates inserted dictionaries by adding `_id`, so insert copies.
        slots_collection.insert_many([deepcopy(slot) for slot in new_slots])

    return new_slots


def delete_slot(slot_id: str) -> bool:
    if not slot_id:
        return False

    result = slots_collection.delete_one({"id": slot_id})
    queue_collection.delete_many({"slotId": slot_id})
    slot_status_collection.delete_one({"slotId": slot_id})
    return result.deleted_count > 0


def list_queue_entries(slot_id: Optional[str] = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if slot_id:
        query["slotId"] = slot_id
    return list(queue_collection.find(query, {"_id": 0}).sort([("joinedAt", 1)]))


def list_waiting_entries(slot_id: Optional[str] = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"status": "waiting"}
    if slot_id:
        query["slotId"] = slot_id
    return list(queue_collection.find(query, {"_id": 0}).sort([("joinedAt", 1)]))


def find_queue_entry(entry_id: str) -> Optional[dict[str, Any]]:
    if not entry_id:
        return None

    entry = queue_collection.find_one({"id": entry_id}, {"_id": 0})
    if entry:
        return entry

    current_status = slot_status_collection.find_one(
        {"current.id": entry_id},
        {"_id": 0},
    )
    if current_status:
        return current_status.get("current")
    return None


def insert_queue_entry(entry: dict[str, Any]) -> dict[str, Any]:
    if not entry:
        raise ValueError("entry cannot be empty")

    entry = deepcopy(entry)
    now = datetime.now(timezone.utc)
    entry.setdefault("createdAt", now)
    entry.setdefault("expiresAt", now + timedelta(days=RETENTION_DAYS))
    queue_collection.insert_one(deepcopy(entry))
    return _without_id(entry)


def delete_queue_entry(entry_id: str) -> bool:
    if not entry_id:
        return False

    queue_result = queue_collection.delete_one({"id": entry_id})
    current_result = slot_status_collection.update_one(
        {"current.id": entry_id},
        {"$unset": {"current": ""}},
    )
    return queue_result.deleted_count > 0 or current_result.modified_count > 0


def delete_first_waiting_entry(slot_id: str) -> bool:
    entry = queue_collection.find_one_and_delete(
        {"slotId": slot_id, "status": "waiting"},
        sort=[("joinedAt", 1)],
        projection={"_id": 0},
    )
    return entry is not None


def pop_next_waiting_entry(slot_id: str) -> Optional[dict[str, Any]]:
    return queue_collection.find_one_and_delete(
        {"slotId": slot_id, "status": "waiting"},
        sort=[("joinedAt", 1)],
        projection={"_id": 0},
    )


def get_current_by_slot() -> dict[str, Optional[dict[str, Any]]]:
    current_by_slot: dict[str, Optional[dict[str, Any]]] = {}
    for status in slot_status_collection.find({}, {"_id": 0, "slotId": 1, "current": 1}):
        current_by_slot[status["slotId"]] = status.get("current")
    return current_by_slot


def get_current_student(slot_id: str) -> Optional[dict[str, Any]]:
    status = slot_status_collection.find_one({"slotId": slot_id}, {"_id": 0})
    return status.get("current") if status else None


def set_current_student(slot_id: str, entry: Optional[dict[str, Any]]) -> None:
    if entry is None:
        clear_current_student(slot_id)
        return

    entry = deepcopy(entry)
    entry.pop("expiresAt", None)
    entry.pop("_id", None)
    slot_status_collection.update_one(
        {"slotId": slot_id},
        {"$set": {"current": entry}, "$setOnInsert": {"servedCount": 0}},
        upsert=True,
    )


def clear_current_student(slot_id: str) -> None:
    slot_status_collection.update_one(
        {"slotId": slot_id},
        {"$unset": {"current": ""}, "$setOnInsert": {"servedCount": 0}},
        upsert=True,
    )


def get_served_by_slot() -> dict[str, int]:
    served_by_slot: dict[str, int] = {}
    for status in slot_status_collection.find({}, {"_id": 0, "slotId": 1, "servedCount": 1}):
        served_by_slot[status["slotId"]] = int(status.get("servedCount", 0))
    return served_by_slot


def increment_served_count(slot_id: str) -> int:
    updated = slot_status_collection.find_one_and_update(
        {"slotId": slot_id},
        {"$inc": {"servedCount": 1}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
        upsert=True,
    )
    return int(updated.get("servedCount", 0)) if updated else 0


def get_settings() -> dict[str, int]:
    settings = settings_collection.find_one({"_id": "app"}, {"_id": 0})
    return {**DEFAULT_SETTINGS, **(settings or {})}


def update_settings(values: dict[str, Any]) -> dict[str, int]:
    settings_collection.update_one(
        {"_id": "app"},
        {"$set": values},
        upsert=True,
    )
    return get_settings()


def list_forecast() -> list[dict[str, Any]]:
    forecast = list(forecast_collection.find({}, {"_id": 0}))
    return forecast or list(DEFAULT_FORECAST)


def append_student_session(session_token: str, entry: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    entry = deepcopy(entry)
    entry.pop("_id", None)
    sessions_collection.insert_one(
        {
            "sessionToken": session_token,
            "entry": entry,
            "createdAt": now,
            "expiresAt": now + timedelta(days=RETENTION_DAYS),
        }
    )


def list_student_sessions(session_token: str) -> list[dict[str, Any]]:
    if not session_token:
        return []

    return [
        session["entry"]
        for session in sessions_collection.find(
            {"sessionToken": session_token},
            {"_id": 0, "entry": 1},
        ).sort([("createdAt", -1)])
    ]


def get_app_snapshot() -> dict[str, Any]:
    settings = get_settings()
    slots = list_slots()
    return {
        "slots": slots,
        "availability": slots,
        "queue": list_queue_entries(),
        "currentBySlot": get_current_by_slot(),
        "servedBySlot": get_served_by_slot(),
        "tasActive": settings["tasActive"],
        "averageHelpMinutes": settings["averageHelpMinutes"],
        "forecast": list_forecast(),
    }
