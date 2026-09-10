"""MongoDB persistence helpers for StudyLine."""

import os
import secrets
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from dotenv import load_dotenv
from pymongo import MongoClient, ReturnDocument

from app.services.scheduling_service import create_slot


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

try:
    import certifi
except ImportError:
    certifi = None


MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "studyline_dev")
RETENTION_DAYS = int(os.getenv("DB_RETENTION_DAYS", "30"))

client_kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 5000}
if certifi is not None and MONGO_URL.startswith("mongodb+srv://"):
    client_kwargs["tlsCAFile"] = certifi.where()

client = MongoClient(MONGO_URL, **client_kwargs)
db = client[MONGO_DB_NAME]

users_collection = db["users"]
sessions_collection = db["auth_sessions"]
courses_collection = db["courses"]
sections_collection = db["sections"]
queue_collection = db["queue"]
slot_status_collection = db["slot_status"]
settings_collection = db["settings"]

DEFAULT_SETTINGS = {"tasActive": 2, "averageHelpMinutes": 7}


def initialize_database() -> None:
    client.admin.command("ping")
    users_collection.create_index("email", unique=True)
    sessions_collection.create_index("token", unique=True)
    sessions_collection.create_index("expiresAt", expireAfterSeconds=0)
    courses_collection.create_index("id", unique=True)
    courses_collection.create_index("code", unique=True)
    courses_collection.create_index("studentShareCode", unique=True)
    courses_collection.create_index("taShareCode", unique=True)
    courses_collection.create_index("taIds")
    courses_collection.create_index("studentIds")
    sections_collection.create_index("id", unique=True)
    sections_collection.create_index("courseId")
    sections_collection.create_index("studentShareCode", unique=True)
    sections_collection.create_index("taShareCode", unique=True)
    sections_collection.create_index([("date", 1), ("startTime", 1)])
    sections_collection.create_index("expiresAt", expireAfterSeconds=0)
    queue_collection.create_index("id", unique=True)
    queue_collection.create_index([("slotId", 1), ("status", 1), ("joinedAt", 1)])
    queue_collection.create_index("expiresAt", expireAfterSeconds=0)
    slot_status_collection.create_index("slotId", unique=True)
    settings_collection.update_one({"_id": "app"}, {"$setOnInsert": DEFAULT_SETTINGS}, upsert=True)
    _seed_if_empty()


def ping_database() -> bool:
    client.admin.command("ping")
    return True


def login_user(email: str, name: str, role: str, google_sub: str | None = None) -> dict[str, Any]:
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise ValueError("email is required")

    now = utc_now()
    user_id = f"user-{normalized_email}"
    user_values = {"email": normalized_email, "updatedAt": now}
    if google_sub:
        user_values["googleSub"] = google_sub

    users_collection.update_one(
        {"email": normalized_email},
        {
            "$set": user_values,
            "$setOnInsert": {
                "id": user_id,
                "name": name.strip() or normalized_email.split("@")[0],
                "createdAt": now,
                "taCourseIds": [],
                "studentCourseIds": [],
            },
            "$addToSet": {"roles": role},
        },
        upsert=True,
    )
    user = users_collection.find_one({"email": normalized_email}, {"_id": 0})
    token = secrets.token_urlsafe(32)
    sessions_collection.insert_one(
        {
            "token": token,
            "userId": user["id"],
            "role": role,
            "createdAt": now,
            "expiresAt": now + timedelta(days=14),
        }
    )
    return {"token": token, "user": user}


def user_for_token(token: str | None) -> Optional[dict[str, Any]]:
    if not token:
        return None
    session = sessions_collection.find_one({"token": token}, {"_id": 0})
    if not session:
        return None
    return users_collection.find_one({"id": session["userId"]}, {"_id": 0})


def logout_user(token: str | None) -> bool:
    if not token:
        return False
    return sessions_collection.delete_one({"token": token}).deleted_count > 0


def update_user_profile(user_id: str, name: str, preferences: dict[str, Any]) -> dict[str, Any]:
    """Update the editable profile fields while preserving account identity."""
    cleaned_name = " ".join((name or "").strip().split())
    if not 2 <= len(cleaned_name) <= 80:
        raise ValueError("username must be between 2 and 80 characters")
    allowed = {"emailNotifications", "compactMode"}
    clean_preferences = {key: bool(value) for key, value in preferences.items() if key in allowed}
    now = utc_now()
    update: dict[str, Any] = {"name": cleaned_name, "updatedAt": now}
    if clean_preferences:
        update["preferences"] = clean_preferences
    updated = users_collection.find_one_and_update(
        {"id": user_id}, {"$set": update}, return_document=ReturnDocument.AFTER, projection={"_id": 0}
    )
    if not updated:
        raise ValueError("user account was not found")
    return updated


def create_course(user: dict[str, Any], code: str, title: str | None = None) -> dict[str, Any]:
    course_code = (code or "").strip().upper()
    if not course_code:
        raise ValueError("course code is required")

    existing = courses_collection.find_one({"code": course_code}, {"_id": 0})
    if existing:
        add_user_to_course(user, existing["id"], "ta")
        return course_by_id(existing["id"])

    course = {
        "id": f"course-{uuid4()}",
        "code": course_code,
        "title": (title or course_code).strip(),
        "taIds": [user["id"]],
        "studentIds": [],
        "createdBy": user["id"],
        "createdAt": utc_now(),
        "studentShareCode": _share_code("S-C"),
        "taShareCode": _share_code("T-C"),
    }
    courses_collection.insert_one(deepcopy(course))
    _add_course_to_user(user["id"], course["id"], "ta")
    return course


def course_by_id(course_id: str) -> Optional[dict[str, Any]]:
    return courses_collection.find_one({"id": course_id}, {"_id": 0})


def update_course(course_id: str, values: dict[str, Any]) -> Optional[dict[str, Any]]:
    updates = {}
    if values.get("code"):
        updates["code"] = values["code"].strip().upper()
    if values.get("title"):
        updates["title"] = values["title"].strip()
    if not updates:
        return course_by_id(course_id)
    courses_collection.update_one({"id": course_id}, {"$set": updates})
    if "code" in updates:
        sections_collection.update_many({"courseId": course_id}, {"$set": {"courseCode": updates["code"]}})
    return course_by_id(course_id)


def list_courses_for_user(user: dict[str, Any], role: str) -> list[dict[str, Any]]:
    membership_field = "taIds" if role == "ta" else "studentIds"
    courses = list(courses_collection.find({membership_field: user["id"]}, {"_id": 0}).sort([("code", 1)]))
    return [_course_with_sections(course, role, user["id"]) for course in courses]


def add_user_to_course(user: dict[str, Any], course_id: str, role: str) -> None:
    course_field = "taIds" if role == "ta" else "studentIds"
    courses_collection.update_one({"id": course_id}, {"$addToSet": {course_field: user["id"]}})
    _add_course_to_user(user["id"], course_id, role)


def join_share_code(user: dict[str, Any], code: str, role: str) -> dict[str, Any]:
    normalized_code = (code or "").strip().upper()
    if not normalized_code:
        raise ValueError("share code is required")

    course_code_field = "taShareCode" if role == "ta" else "studentShareCode"
    section_code_field = course_code_field
    course = courses_collection.find_one({course_code_field: normalized_code}, {"_id": 0})
    section = sections_collection.find_one({section_code_field: normalized_code}, {"_id": 0})

    if not course and not section:
        raise LookupError("share code not found")

    if section:
        course = course_by_id(section["courseId"])
        if role == "ta":
            sections_collection.update_one({"id": section["id"]}, {"$addToSet": {"taIds": user["id"]}})
        record_section_participation(section["id"], user["id"], role)

    add_user_to_course(user, course["id"], role)
    return {"course": _course_with_sections(course_by_id(course["id"]), role, user["id"]), "section": section}


def create_section(
    user: dict[str, Any],
    course_id: str,
    date_value: str,
    start_time: str,
    end_time: str,
    location: str,
    zoom_link: str = "",
    title: str = "",
) -> dict[str, Any]:
    course = course_by_id(course_id)
    if not course:
        raise LookupError("course not found")

    add_user_to_course(user, course_id, "ta")
    section = create_slot(
        date=date_value[:10],
        start_time=start_time[:5],
        ta_name=user.get("name") or "TA",
        location=location.strip() or "Office Hours Room",
        course_id=course_id,
        course_code=course["code"],
    )
    section["id"] = f"section-{uuid4()}"
    section["endTime"] = end_time[:5]
    section["title"] = title.strip() or f"{user.get('name') or 'TA'}'s Office Hour"
    section["zoomLink"] = zoom_link.strip()
    section["taIds"] = [user["id"]]
    section["participantTaIds"] = [user["id"]]
    section["participantStudentIds"] = []
    section["createdBy"] = user["id"]
    section["createdAt"] = utc_now()
    section["saved"] = False
    section["studentShareCode"] = _share_code("S-S")
    section["taShareCode"] = _share_code("T-S")
    section["expiresAt"] = _section_expiry(section)
    sections_collection.insert_one(deepcopy(section))
    return _without_id(section)


def update_section(section_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    section = section_by_id(section_id)
    if not section:
        return None

    allowed = {"courseId", "title", "date", "startTime", "endTime", "location", "zoomLink", "status"}
    next_values = {key: value for key, value in updates.items() if key in allowed and value is not None}
    if "courseId" in next_values:
        course = course_by_id(next_values["courseId"])
        if course:
            next_values["courseCode"] = course["code"]
        else:
            next_values.pop("courseId", None)

    labels = {
        "title": "Title", "date": "Date", "startTime": "Start time", "endTime": "End time",
        "location": "Location", "zoomLink": "Zoom link", "status": "Status",
        "courseCode": "Course",
    }
    changes = [
        {"field": key, "label": label, "before": section.get(key) or "", "after": next_values[key]}
        for key, label in labels.items()
        if key in next_values and (section.get(key) or "") != next_values[key]
    ]
    if changes and updates.get("highlightChange"):
        next_values["changeHighlighted"] = True
        next_values["changes"] = changes
        next_values["changeNotice"] = "; ".join(
            f"{change['label']}: {change['before'] or 'Not set'} → {change['after'] or 'Not set'}"
            for change in changes
        )
        next_values["changedAt"] = utc_now()
    elif changes:
        next_values["changeHighlighted"] = False
        next_values["changeNotice"] = ""
        next_values["changes"] = []

    if updates.get("saved") is True:
        next_values["saved"] = True
        update_doc = {"$set": next_values, "$unset": {"expiresAt": ""}}
    else:
        merged = {**section, **next_values}
        next_values["expiresAt"] = _section_expiry(merged)
        update_doc = {"$set": next_values}

    sections_collection.update_one({"id": section_id}, update_doc)
    return section_by_id(section_id)


def delete_section(section_id: str) -> bool:
    result = sections_collection.delete_one({"id": section_id})
    queue_collection.delete_many({"slotId": section_id})
    slot_status_collection.delete_one({"slotId": section_id})
    return result.deleted_count > 0


def section_by_id(section_id: str) -> Optional[dict[str, Any]]:
    return sections_collection.find_one({"id": section_id}, {"_id": 0})


def section_context(section_id: str) -> Optional[dict[str, Any]]:
    section = section_by_id(section_id)
    if not section:
        return None
    return {"section": section, "course": course_by_id(section["courseId"])}


def record_section_participation(section_id: str, user_id: str, role: str) -> None:
    field = "participantTaIds" if role == "ta" else "participantStudentIds"
    sections_collection.update_one({"id": section_id}, {"$addToSet": {field: user_id}})


def find_slot(slot_id: str) -> Optional[dict[str, Any]]:
    return section_by_id(slot_id)


def list_slots(course_id: Optional[str] = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if course_id:
        query["courseId"] = course_id
    return list(sections_collection.find(query, {"_id": 0}).sort([("date", 1), ("startTime", 1)]))


def insert_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inserted = []
    for slot in slots:
        section = deepcopy(slot)
        section.setdefault("id", f"section-{uuid4()}")
        section.setdefault("studentShareCode", _share_code("S-S"))
        section.setdefault("taShareCode", _share_code("T-S"))
        section.setdefault("saved", False)
        section["expiresAt"] = _section_expiry(section)
        sections_collection.insert_one(deepcopy(section))
        inserted.append(_without_id(section))
    return inserted


def delete_slot(slot_id: str) -> bool:
    return delete_section(slot_id)


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
    entry = queue_collection.find_one({"id": entry_id}, {"_id": 0})
    if entry:
        return entry
    status_doc = slot_status_collection.find_one({"current.id": entry_id}, {"_id": 0})
    return status_doc.get("current") if status_doc else None


def insert_queue_entry(entry: dict[str, Any]) -> dict[str, Any]:
    entry = deepcopy(entry)
    now = utc_now()
    entry.setdefault("createdAt", now)
    entry.setdefault("expiresAt", now + timedelta(days=RETENTION_DAYS))
    queue_collection.insert_one(deepcopy(entry))
    if entry.get("slotId") and entry.get("studentUserId"):
        record_section_participation(entry["slotId"], entry["studentUserId"], "student")
    return _without_id(entry)


def delete_queue_entry(entry_id: str) -> bool:
    queue_result = queue_collection.delete_one({"id": entry_id})
    current_result = slot_status_collection.update_one({"current.id": entry_id}, {"$unset": {"current": ""}})
    return queue_result.deleted_count > 0 or current_result.modified_count > 0


def pop_next_waiting_entry(slot_id: str) -> Optional[dict[str, Any]]:
    return queue_collection.find_one_and_delete(
        {"slotId": slot_id, "status": "waiting"},
        sort=[("joinedAt", 1)],
        projection={"_id": 0},
    )


def get_current_by_slot() -> dict[str, Optional[dict[str, Any]]]:
    result: dict[str, Optional[dict[str, Any]]] = {}
    for status in slot_status_collection.find({}, {"_id": 0, "slotId": 1, "current": 1}):
        result[status["slotId"]] = status.get("current")
    return result


def get_current_student(slot_id: str) -> Optional[dict[str, Any]]:
    status = slot_status_collection.find_one({"slotId": slot_id}, {"_id": 0})
    return status.get("current") if status else None


def set_current_student(slot_id: str, entry: Optional[dict[str, Any]]) -> None:
    if entry is None:
        clear_current_student(slot_id)
        return
    entry = deepcopy(entry)
    entry.pop("_id", None)
    entry.pop("expiresAt", None)
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


def increment_served_count(slot_id: str) -> int:
    updated = slot_status_collection.find_one_and_update(
        {"slotId": slot_id},
        {"$inc": {"servedCount": 1}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
        upsert=True,
    )
    return int(updated.get("servedCount", 0)) if updated else 0


def get_served_by_slot() -> dict[str, int]:
    result: dict[str, int] = {}
    for status in slot_status_collection.find({}, {"_id": 0, "slotId": 1, "servedCount": 1}):
        result[status["slotId"]] = int(status.get("servedCount", 0))
    return result


def get_settings() -> dict[str, int]:
    settings = settings_collection.find_one({"_id": "app"}, {"_id": 0})
    return {**DEFAULT_SETTINGS, **(settings or {})}


def get_app_snapshot(course_id: Optional[str] = None) -> dict[str, Any]:
    settings = get_settings()
    slots = list_slots(course_id=course_id)
    return {
        "slots": slots,
        "availability": slots,
        "queue": list_queue_entries(),
        "currentBySlot": get_current_by_slot(),
        "servedBySlot": get_served_by_slot(),
        "tasActive": settings["tasActive"],
        "averageHelpMinutes": settings["averageHelpMinutes"],
        "forecast": [],
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def serialize(document: Any) -> Any:
    if isinstance(document, list):
        return [serialize(item) for item in document]
    if isinstance(document, dict):
        return {key: serialize(value) for key, value in document.items() if key != "_id"}
    if isinstance(document, datetime):
        return document.isoformat()
    return document


def _without_id(document: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if document is None:
        return None
    document = dict(document)
    document.pop("_id", None)
    return document


def _share_code(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3).upper()}"


def _add_course_to_user(user_id: str, course_id: str, role: str) -> None:
    field = "taCourseIds" if role == "ta" else "studentCourseIds"
    users_collection.update_one({"id": user_id}, {"$addToSet": {field: course_id}})


def _course_with_sections(course: dict[str, Any], role: str, user_id: str) -> dict[str, Any]:
    now_key = date.today().isoformat()
    sections = list(sections_collection.find({"courseId": course["id"]}, {"_id": 0}).sort([("date", 1), ("startTime", 1)]))
    upcoming = [section for section in sections if section.get("date", "") >= now_key and section.get("status") != "cancelled"]
    participant_field = "participantTaIds" if role == "ta" else "participantStudentIds"
    past = [
        section
        for section in sections
        if (section.get("date", "") < now_key or section.get("status") == "cancelled")
        and user_id in section.get(participant_field, [])
    ]
    return {**course, "upcomingSections": upcoming, "pastSections": past}


def _section_expiry(section: dict[str, Any]) -> datetime:
    end_at = datetime.fromisoformat(f"{section['date']}T{section['endTime']}:00").replace(tzinfo=timezone.utc)
    return end_at + timedelta(days=RETENTION_DAYS)


def _seed_if_empty() -> None:
    if courses_collection.count_documents({}) > 0:
        return

    demo = login_user("demo.ta@studyline.local", "Bobby", "ta")["user"]
    course = create_course(demo, "CS 101", "Intro Computer Science")
    today = date.today().isoformat()
    create_section(demo, course["id"], today, "11:30", "12:00", "Library 204", "")
