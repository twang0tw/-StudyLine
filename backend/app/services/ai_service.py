"""Question triage helpers with an optional OpenAI-backed analysis."""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


def analyze_question(
    course: str | None,
    need: str | None,
    message: str | None,
    file: Any = None,
    accuracy: str = "low",
) -> dict[str, Any]:
    if os.getenv("OPENAI_API_KEY"):
        try:
            return _analyze_with_openai(course, need, message, file)
        except Exception:
            # Queue entry must remain available if the model service is unavailable.
            pass

    return _analyze_locally(course, need, message, file)


def _analyze_with_openai(course, need, message, file) -> dict[str, Any]:
    attachment = ""
    if file:
        attachment = f"\nAttachment metadata: {file.get('name', 'file')} ({file.get('type', 'unknown')})"
    response = OpenAI(timeout=8.0).responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "Triage an office-hours question. Summarize the student's need in one short sentence, "
            "choose up to three concise topic tags, and estimate 3-25 minutes of TA help."
        ),
        input=f"Course: {course or 'General'}\nNeed: {need or 'Office hours help'}\nQuestion: {message or 'No details'}{attachment}",
        text={
            "format": {
                "type": "json_schema",
                "name": "office_hours_triage",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                        "estimatedHelpMinutes": {"type": "integer", "minimum": 3, "maximum": 25},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                    "required": ["summary", "tags", "estimatedHelpMinutes", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        store=False,
    )
    result = json.loads(response.output_text)
    return {
        "summary": str(result["summary"]).strip()[:240],
        "tags": [str(tag).strip()[:40] for tag in result["tags"][:3]],
        "estimatedHelpMinutes": max(3, min(25, int(result["estimatedHelpMinutes"]))),
        "confidence": result["confidence"],
        "source": "openai",
    }


def _analyze_locally(course, need, message, file) -> dict[str, Any]:
    text = " ".join(part for part in [course, need, message] if part).lower()
    minutes = 7
    confidence = "medium"

    if any(word in text for word in ["debug", "error", "traceback", "broken", "bug"]):
        minutes = 10
    elif any(word in text for word in ["exam", "review", "proof", "concept"]):
        minutes = 12
    elif any(word in text for word in ["quick", "syntax", "clarify"]):
        minutes = 5
        confidence = "low"

    if file:
        minutes += 2

    return {
        "summary": (message or need or "Student needs office-hours support.").strip()[:240],
        "tags": [tag for tag in ["debugging", "concept", "review"] if tag in text][:3],
        "estimatedHelpMinutes": max(3, min(25, minutes)),
        "confidence": confidence,
        "source": "local",
    }
