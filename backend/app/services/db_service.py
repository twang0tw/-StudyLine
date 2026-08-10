"""MongoDB storage helpers for the FastAPI migration."""

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from app.services.scheduling_service import create_slot, slot_id_for


load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "studyline_dev")
RETENTION_DAYS = int(os.getenv("DB_RETENTION_DAYS", "30"))

client = AsyncIOMotorClient(MONGO_URL)
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


async def initialize_database() -> None:
    await slots_collection.create_index("id", unique=True)
    await slots_collection.create_index([("date", 1), ("startTime", 1)])
    await queue_collection.create_index("id", unique=True)
    await queue_collection.create_index([("slotId", 1), ("status", 1), ("joinedAt", 1)])
    await queue_collection.create_index("expiresAt", expireAfterSeconds=0)
    await slot_status_collection.create_index("slotId", unique=True)
    await sessions_collection.create_index([("sessionToken", 1), ("createdAt", -1)])
    await sessions_collection.create_index("expiresAt", expireAfterSeconds=0)

    await settings_collection.update_one(
        {"_id": "app"},
        {"$setOnInsert": DEFAULT_SETTINGS},
        upsert=True,
    )

    if await forecast_collection.count_documents({}) == 0:
        await forecast_collection.insert_many(DEFAULT_FORECAST)

    if await slots_collection.count_documents({}) == 0:
        await insert_slots(_default_slots())


async def list_slots() -> list[dict[str, Any]]:
    return await slots_collection.find({}, {"_id": 0}).sort(
        [("date", 1), ("startTime", 1)]
    ).to_list(length=None)


async def find_slot(slot_id: str) -> Optional[dict[str, Any]]:
    if not slot_id:
        return None
    return await slots_collection.find_one({"id": slot_id}, {"_id": 0})


async def insert_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not slots:
        return []

    existing_ids = {
        slot["id"]
        async for slot in slots_collection.find(
            {"id": {"$in": [slot["id"] for slot in slots]}},
            {"id": 1, "_id": 0},
        )
    }
    new_slots = [slot for slot in slots if slot["id"] not in existing_ids]

    if new_slots:
        await slots_collection.insert_many(new_slots)

    return new_slots


async def delete_slot(slot_id: str) -> bool:
    if not slot_id:
        return False

    result = await slots_collection.delete_one({"id": slot_id})
    await queue_collection.delete_many({"slotId": slot_id})
    await slot_status_collection.delete_one({"slotId": slot_id})
    return result.deleted_count > 0


async def list_queue_entries(slot_id: Optional[str] = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if slot_id:
        query["slotId"] = slot_id
    return await queue_collection.find(query, {"_id": 0}).sort(
        [("joinedAt", 1)]
    ).to_list(length=None)


async def list_waiting_entries(slot_id: Optional[str] = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"status": "waiting"}
    if slot_id:
        query["slotId"] = slot_id
    return await queue_collection.find(query, {"_id": 0}).sort(
        [("joinedAt", 1)]
    ).to_list(length=None)


async def find_queue_entry(entry_id: str) -> Optional[dict[str, Any]]:
    if not entry_id:
        return None

    entry = await queue_collection.find_one({"id": entry_id}, {"_id": 0})
    if entry:
        return entry

    current_status = await slot_status_collection.find_one(
        {"current.id": entry_id},
        {"_id": 0},
    )
    if current_status:
        return current_status.get("current")
    return None


async def insert_queue_entry(entry: dict[str, Any]) -> dict[str, Any]:
    if not entry:
        raise ValueError("entry cannot be empty")

    now = datetime.now(timezone.utc)
    entry.setdefault("createdAt", now)
    entry.setdefault("expiresAt", now + timedelta(days=RETENTION_DAYS))
    await queue_collection.insert_one(entry)
    return entry


async def delete_queue_entry(entry_id: str) -> bool:
    if not entry_id:
        return False

    queue_result = await queue_collection.delete_one({"id": entry_id})
    current_result = await slot_status_collection.update_one(
        {"current.id": entry_id},
        {"$unset": {"current": ""}},
    )
    return queue_result.deleted_count > 0 or current_result.modified_count > 0


async def delete_first_waiting_entry(slot_id: str) -> bool:
    entry = await queue_collection.find_one_and_delete(
        {"slotId": slot_id, "status": "waiting"},
        sort=[("joinedAt", 1)],
        projection={"_id": 0},
    )
    return entry is not None


async def pop_next_waiting_entry(slot_id: str) -> Optional[dict[str, Any]]:
    return await queue_collection.find_one_and_delete(
        {"slotId": slot_id, "status": "waiting"},
        sort=[("joinedAt", 1)],
        projection={"_id": 0},
    )


async def get_current_by_slot() -> dict[str, Optional[dict[str, Any]]]:
    current_by_slot: dict[str, Optional[dict[str, Any]]] = {}
    async for status in slot_status_collection.find({}, {"_id": 0, "slotId": 1, "current": 1}):
        current_by_slot[status["slotId"]] = status.get("current")
    return current_by_slot


async def get_current_student(slot_id: str) -> Optional[dict[str, Any]]:
    status = await slot_status_collection.find_one({"slotId": slot_id}, {"_id": 0})
    return status.get("current") if status else None


async def set_current_student(slot_id: str, entry: Optional[dict[str, Any]]) -> None:
    if entry is None:
        await clear_current_student(slot_id)
        return

    entry.pop("expiresAt", None)
    await slot_status_collection.update_one(
        {"slotId": slot_id},
        {"$set": {"current": entry}, "$setOnInsert": {"servedCount": 0}},
        upsert=True,
    )


async def clear_current_student(slot_id: str) -> None:
    await slot_status_collection.update_one(
        {"slotId": slot_id},
        {"$unset": {"current": ""}, "$setOnInsert": {"servedCount": 0}},
        upsert=True,
    )


async def get_served_by_slot() -> dict[str, int]:
    served_by_slot: dict[str, int] = {}
    async for status in slot_status_collection.find({}, {"_id": 0, "slotId": 1, "servedCount": 1}):
        served_by_slot[status["slotId"]] = int(status.get("servedCount", 0))
    return served_by_slot


async def increment_served_count(slot_id: str) -> int:
    updated = await slot_status_collection.find_one_and_update(
        {"slotId": slot_id},
        {"$inc": {"servedCount": 1}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
        upsert=True,
    )
    return int(updated.get("servedCount", 0)) if updated else 0


async def get_settings() -> dict[str, int]:
    settings = await settings_collection.find_one({"_id": "app"}, {"_id": 0})
    return {**DEFAULT_SETTINGS, **(settings or {})}


async def update_settings(values: dict[str, Any]) -> dict[str, int]:
    await settings_collection.update_one(
        {"_id": "app"},
        {"$set": values},
        upsert=True,
    )
    return await get_settings()


async def list_forecast() -> list[dict[str, Any]]:
    forecast = await forecast_collection.find({}, {"_id": 0}).to_list(length=None)
    return forecast or list(DEFAULT_FORECAST)


async def append_student_session(session_token: str, entry: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    await sessions_collection.insert_one(
        {
            "sessionToken": session_token,
            "entry": entry,
            "createdAt": now,
            "expiresAt": now + timedelta(days=RETENTION_DAYS),
        }
    )


async def list_student_sessions(session_token: str) -> list[dict[str, Any]]:
    if not session_token:
        return []

    sessions = await sessions_collection.find(
        {"sessionToken": session_token},
        {"_id": 0, "entry": 1},
    ).sort([("createdAt", -1)]).to_list(length=None)
    return [session["entry"] for session in sessions]


async def get_app_snapshot() -> dict[str, Any]:
    settings = await get_settings()
    slots = await list_slots()
    return {
        "slots": slots,
        "availability": slots,
        "queue": await list_queue_entries(),
        "currentBySlot": await get_current_by_slot(),
        "servedBySlot": await get_served_by_slot(),
        "tasActive": settings["tasActive"],
        "averageHelpMinutes": settings["averageHelpMinutes"],
        "forecast": await list_forecast(),
    }
