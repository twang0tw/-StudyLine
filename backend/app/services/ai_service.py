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

    text = result