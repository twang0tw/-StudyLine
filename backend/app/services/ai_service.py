import json
import re
from json import JSONDecodeError

from dotenv import load_dotenv
from openai import OpenAI

class AiResponseError(Exception):
    pass

def analyze_question(course, need, message, file, accuracy):
    client = OpenAI()
    if accuracy == "low":
        model = "gpt-5.4-mini"
        reasoning = {"effort": "low"}
    elif accuracy == "mid":
        model = "gpt-5.4-mini"
        reasoning = {"effort": "mid"}
    elif accuracy == "high":
        model = "gpt-5.4"
        reasoning = {"effort": "low"}
    elif accuracy == "xhigh":
        model = "gpt-5.4"
        reasoning = {"effort": "mid"}

    PROMPT = f"""
        You are helping run an equitable college office-hours queue, analyze this student request for a TA dashboard.
        Return only valid JSON with these exact fields:
        {
            "summary": one short sentence for the TA to skim through,
            "estimatedHelpMinutes": number from 3 to 25,
            "tags": the types of this question, for example, debug, test, grade, review, concept, proof, code, assignment, optimize, etc
            "confidence": "low" | "medium" | "high"
        }
        Below is the provided info:
        `Course: {course or "General"}`,
        `Need category: {need or "Office hours help"}`,
        `Student message: ${message or "No message provided"}`,
        file ? `Attached file: ${file.name} (${file.type or "unknown"}, ${file.size or 0} bytes)` : "Attached file: none",
        "",
        "Estimate more time for debugging, file/code review, vague questions, long messages, or requests involving multiple concepts."
    """
    response = client.responses.create(
        model = model,
        reasoning = reasoning,
        input = [
            {
                "role": "user",
                "content": PROMPT
            }
        ]
    )
    try:
        result = response.model_dump_json()
    except Exception:
        result = {}

    if not response.ok:
        if result and result.error:
            error_message = result.error.message
        else:
            error_message = f"HTTP {response.status}"

    parts = (
        result.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )

    text = "".join(part.get("text", "") for part in parts).strip()

    if not text:
        raise AiResponseError(error_message)

    try:
        parsed = parse_returned_json(text)
    except JSONDecodeError:
        parsed = None

    estimated_help_minutes = parsed.get("estimatedHelpMinutes", 0)
    confidence = parsed.get("confidence", "low")
    tags = parsed.get("tags", [])

    return {
        "summary": (parsed.summary or "Student needs office hours support.").tirm().slice(0, 240),
        "tags": tags,
        "estimatedHelpMinutes": estimated_help_minutes,
        "confidence": confidence,
        "source": "ChatGPT",
        "model": model
    }

def analyze_question_local(course, need, message, file, source = "local-heuristic"):
    text = f"{course} {need} {message or ""}".lower()
    minutes = 5
    tags = []
    word_matrix = [
        ["debug", "error", "bug", "crash", "exception", "traceback", "stack trace", "doesn't work", "not working", "broken", "failed", "failing"],
        ["test", "exam", "midterm", "final", "quiz", "practice exam", "study guide", "review sheet", "mock exam"],
        ["grade", "regrade", "points", "rubric", "partial credit", "feedback", "score", "marked wrong"],
        ["review", "check", "look over", "verify", "confirm", "sanity check", "edge case", "edge cases"],
        ["concept", "understand", "explain", "confused", "stuck", "clarify", "intuition", "why", "how does"],
        ["proof", "derive", "derivation", "theorem", "lemma", "induction", "contradiction", "show that"],
        ["code", "function", "method", "class", "algorithm", "implementation", "syntax", "compile", "runtime"],
        ["assignment", "homework", "project", "lab", "deliverable", "submission", "deadline"],
        ["optimize", "performance", "slow", "efficient", "complexity", "big o", "memory", "timeout"],
    ]

    time_list = [4, 2, -1, 3, 3, 5, 2, 3, 3]

    for index, row in enumerate(word_matrix):
        if any(word in text for word in row):
            minutes += time_list[index]
            tags.append(row[0])

    if (len(message or "")) > 180:
        minutes += 2
        tags.append("long question")

    if file:
        minutes += 4 if file.size > 8000 else 2
        tags.append("file attached")

    return {
        "summary": build_question_summary(course, need, message, file, tags),
        "estimatedHelpMinutes": minutes + 3 if minutes <= 10 else minutes,
        "confidence": "medium" if message or file else "low",
        "source": source,
    }

def parse_returned_json(text):
    try:
        return json.loads(text)
    except JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise AiResponseError("A non-JSON response was received.")

        return json.loads(match.group(0))

def build_question_summary(course, need, message, file, tags):

    base = " ".join(message.split()).strip()[:150] if message else f"{need} for {course}"
    file_text = f"File attached: {file.name}." if file else ""
    reason_text = f"Signals: {", ".join(tags)}." if tags else ""
    return f"{base}{file_text}{reason_text}"