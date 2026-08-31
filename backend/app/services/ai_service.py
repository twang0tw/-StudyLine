"""Question triage helpers.

The app can work without an AI key. This local fallback keeps the queue usable
while still returning the same response shape as an AI-backed implementation.
"""

from typing import Any


def analyze_question(
    course: str | None,
    need: str | None,
    message: str | None,
    file: Any = None,
    accuracy: str = "low",
) -> dict[str, Any]:
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
