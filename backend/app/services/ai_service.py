"""AI-assisted question triage.

This service mirrors the old `analyzeQuestion` behavior from `server.js`:
try an AI provider first, then fall back to a local heuristic if the provider
is unavailable or returns something unusable.
"""

import json
import re
from json import JSONDecodeError
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # The backend can still run with environment variables provided directly.
    pass


class AiResponseError(Exception):
    """Raised when the AI provider returns an invalid triage response."""


def analyze_question(
    course: Optional[str],
    need: Optional[str],
    message: Optional[str],
    file: Any,
    accuracy: str = "low",
) -> Dict[str, Any]:
    """Analyze a student question with AI, falling back to local heuristics."""

    try:
        return analyze_question_with_openai(course, need, message, file, accuracy)
    except Exception:
        return analyze_question_local(course, need, message, file)


def analyze_question_with_openai(
    course: Optional[str],
    need: Optional[str],
    message: Optional[str],
    file: Any,
    accuracy: str = "low",
) -> Dict[str, Any]:
    """Call OpenAI and normalize the returned JSON into our app contract."""

    try:
        from openai import OpenAI
    except ImportError as error:
        raise AiResponseError("The openai package is not installed.") from error

    model, reasoning = _model_settings_for_accuracy(accuracy)
    client = OpenAI()
    prompt = _build_prompt(course, need, message, file)

    response = client.responses.create(
        model=model,
        reasoning=reasoning,
        input=[{"role": "user", "content": prompt}],
    )
    text = _extract_response_text(response)

    if not text:
        raise AiResponseError("OpenAI returned no text.")

    parsed = parse_returned_json(text)
    estimated_help_minutes = _clamp_int(parsed.get("estimatedHelpMinutes"), 3, 25, 8)
    confidence = parsed.get("confidence") if parsed.get("confidence") in {"low", "medium", "high"} else "medium"
    tags = parsed.get("tags") if isinstance(parsed.get("tags"), list) else []

    return {
        "summary": str(parsed.get("summary") or "Student needs office hours support.").strip()[:240],
        "tags": tags,
        "estimatedHelpMinutes": estimated_help_minutes,
        "confidence": confidence,
        "source": "openai",
        "model": model,
    }


def analyze_question_local(
    course: Optional[str],
    need: Optional[str],
    message: Optional[str],
    file: Any,
    source: str = "local-heuristic",
) -> Dict[str, Any]:
    """Local fallback when AI is unavailable."""

    text = f"{course or ''} {need or ''} {message or ''}".lower()
    minutes = 6
    tags = []
    word_matrix = [
        ("debug", ["debug", "error", "bug", "crash", "exception", "traceback", "stack trace", "doesn't work", "not working", "broken", "failed", "failing"], 4),
        ("test", ["test", "exam", "midterm", "final", "quiz", "practice exam", "study guide", "mock exam"], 2),
        ("grade", ["grade", "regrade", "points", "rubric", "partial credit", "feedback", "score", "marked wrong"], -1),
        ("review", ["review", "check", "look over", "verify", "confirm", "sanity check", "edge case", "edge cases"], 3),
        ("concept", ["concept", "understand", "explain", "confused", "stuck", "clarify", "intuition", "why", "how does"], 2),
        ("proof", ["proof", "derive", "derivation", "theorem", "lemma", "induction", "contradiction", "show that"], 3),
        ("code", ["code", "function", "method", "class", "algorithm", "implementation", "syntax", "compile", "runtime"], 2),
        ("assignment", ["assignment", "homework", "project", "lab", "deliverable", "submission", "deadline"], 3),
        ("optimize", ["optimize", "performance", "slow", "efficient", "complexity", "big o", "memory", "timeout"], 3),
    ]

    for tag, words, minute_delta in word_matrix:
        if any(word in text for word in words):
            minutes += minute_delta
            tags.append(tag)

    if len(message or "") > 180:
        minutes += 2
        tags.append("detailed question")

    if file:
        minutes += 4 if _file_size(file) > 8000 else 2
        tags.append("attached file")

    return {
        "summary": build_question_summary(course, need, message, file, tags),
        "tags": tags,
        "estimatedHelpMinutes": max(3, min(25, minutes)),
        "confidence": "medium" if message or file else "low",
        "source": source,
    }


def parse_returned_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise AiResponseError("A non-JSON response was received.")

        return json.loads(match.group(0))


def build_question_summary(
    course: Optional[str],
    need: Optional[str],
    message: Optional[str],
    file: Any,
    tags: List[str],
) -> str:
    base = " ".join(message.split()).strip()[:150] if message else f"{need or 'Office hours help'} for {course or 'General'}"
    file_text = f" File attached: {_file_name(file)}." if file else ""
    reason_text = f" Signals: {', '.join(tags)}." if tags else ""
    return f"{base}{file_text}{reason_text}"


def _build_prompt(course: Optional[str], need: Optional[str], message: Optional[str], file: Any) -> str:
    file_text = (
        f"Attached file: {_file_name(file)} ({_file_type(file)}, {_file_size(file)} bytes)"
        if file
        else "Attached file: none"
    )
    return (
    f"""
        You are helping run an equitable college office-hours queue.
        Analyze this student request for a TA dashboard.
        Return only valid JSON with these exact fields:
        {{
          "summary": "one short sentence for the TA",
          "estimatedHelpMinutes": 3,
          "tags": ["debug"],
          "confidence": "low"
        }}
        
        Course: {course or "General"}
        Need category: {need or "Office hours help"}
        Student message: {message or "No message provided"}
        {file_text}
        
        Estimate more time for debugging, file/code review, vague questions, long messages, or requests involving multiple concepts.
    """.strip())


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text).strip()

    model_dump = getattr(response, "model_dump", None)
    data = model_dump() if callable(model_dump) else {}
    chunks = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks).strip()


def _model_settings_for_accuracy(accuracy: str) -> Tuple[str, Dict[str, str]]:
    settings = {
        "low": ("gpt-5.4-mini", {"effort": "low"}),
        "mid": ("gpt-5.4-mini", {"effort": "medium"}),
        "medium": ("gpt-5.4-mini", {"effort": "medium"}),
        "high": ("gpt-5.4", {"effort": "low"}),
        "xhigh": ("gpt-5.4", {"effort": "medium"}),
    }
    return settings.get(accuracy, settings["low"])


def _clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def _file_name(file: Any) -> str:
    if isinstance(file, dict):
        return str(file.get("name") or "Attached file")
    return str(getattr(file, "name", "Attached file"))


def _file_type(file: Any) -> str:
    if isinstance(file, dict):
        return str(file.get("type") or "unknown")
    return str(getattr(file, "type", "unknown"))


def _file_size(file: Any) -> int:
    if isinstance(file, dict):
        return int(file.get("size") or 0)
    return int(getattr(file, "size", 0) or 0)
