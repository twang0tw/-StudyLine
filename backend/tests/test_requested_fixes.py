import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services import ai_service, db_service
from app.services.scheduling_service import estimate_wait
from app.services.state_service import build_state


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def render_frontend(expression: str, page: str = "test") -> str:
    script = f"""
const fs = require("fs");
const vm = require("vm");
const notifications = [];
class Notification {{
  static permission = "granted";
  static requestPermission = async () => "granted";
  constructor(title, options) {{ notifications.push({{ title, ...options }}); }}
}}
const storage = {{ getItem: () => null, setItem: () => {{}}, removeItem: () => {{}} }};
const context = {{
  console,
  Date,
  URL,
  URLSearchParams,
  history: {{ replaceState: () => {{}} }},
  setInterval: () => 0,
  setTimeout: () => 0,
  fetch: async () => ({{ ok: true, text: async () => "{{}}" }}),
  Notification,
  notifications,
  window: {{ Notification, localStorage: storage, sessionStorage: storage, location: {{ search: "", origin: "http://test" }} }},
  document: {{
    hidden: false,
    body: {{ dataset: {{ page: {json.dumps(page)} }}, classList: {{ toggle: () => {{}} }} }},
    querySelector: () => ({{ innerHTML: "", addEventListener: () => {{}} }}),
    querySelectorAll: () => [],
  }},
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync("app.js", "utf8"), context);
process.stdout.write(String(vm.runInContext({json.dumps(expression)}, context)));
"""
    return subprocess.run(
        ["node", "-e", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_empty_line_has_zero_wait():
    assert estimate_wait([], tas_active=2, average_help_minutes=7) == 0


def test_state_uses_section_ta_count():
    slot = {
        "id": "section-1",
        "date": "2026-09-10",
        "startTime": "10:00",
        "endTime": "11:00",
        "taIds": ["ta-section"],
        "participantTaIds": ["ta-section"],
    }
    state = build_state([slot], [], {}, {}, requested_slot_id=slot["id"], tas_active=8)
    assert state["live"]["tasActive"] == 1


def test_section_title_and_holders_are_stored():
    user = {"id": "ta-creator", "name": "Max Cai"}
    course = {"id": "course-1", "code": "CS 101", "taIds": ["ta-creator", "ta-other"]}
    with (
        patch.object(db_service, "course_by_id", return_value=course),
        patch.object(db_service, "add_user_to_course"),
        patch.object(db_service, "_section_expiry", return_value=None),
        patch.object(db_service, "sections_collection"),
    ):
        section = db_service.create_section(
            user, course["id"], "2026-09-10", "10:00", "11:00", "Room 1", "https://zoom.us/j/1",
            title="Max Cai's Office Hour",
        )

    assert section["title"] == "Max Cai's Office Hour"
    assert section["taIds"] == ["ta-creator"]


def test_logout_invalidates_server_session():
    with patch.object(db_service, "sessions_collection") as sessions:
        sessions.delete_one.return_value.deleted_count = 1
        assert db_service.logout_user("secret-token") is True
        sessions.delete_one.assert_called_once_with({"token": "secret-token"})


def test_student_section_renders_clickable_zoom_url_and_holder_count():
    section = {
        "id": "section-1",
        "title": "Max Cai's Office Hour",
        "zoomLink": "https://zoom.us/j/123",
        "taIds": ["ta-1", "ta-2"],
        "participantTaIds": ["ta-1", "ta-2"],
    }
    html = render_frontend(f"renderSectionAccess({json.dumps(section)})")
    assert 'href="https://zoom.us/j/123"' in html
    assert "https://zoom.us/j/123" in html
    assert "2 TAs holding this section" in html


def test_section_title_appears_in_section_block():
    section = {
        "id": "section-1",
        "title": "Max Cai's Office Hour",
        "date": "2026-09-10",
        "startTime": "10:00",
        "endTime": "11:00",
        "location": "Room 1",
    }
    html = render_frontend(f"renderSectionMini({json.dumps(section)}, true)")
    assert "Max Cai&#039;s Office Hour" in html


def test_history_uses_short_expiration_date():
    section = {
        "id": "section-1",
        "date": "2026-09-01",
        "startTime": "10:00",
        "endTime": "11:00",
        "location": "Room 1",
        "expiresAt": "2026-10-01T15:30:00Z",
        "saved": False,
    }
    html = render_frontend(f"renderPastSections([{json.dumps(section)}])")
    assert "Oct 1" in html
    assert "2026-10-01T15:30:00" not in html


def test_next_student_notification_is_sent_once_per_queue_entry():
    expression = """
      queueToken = "queue-1";
      queueNotificationEnabled = true;
      maybeNotifyNextStudent(
        {code: "CS 101"},
        {title: "Max Cai's Office Hour"},
        {queue: {status: "next"}}
      );
      maybeNotifyNextStudent(
        {code: "CS 101"},
        {title: "Max Cai's Office Hour"},
        {queue: {status: "next"}}
      );
      JSON.stringify(notifications);
    """
    notifications = json.loads(render_frontend(expression, page="student"))
    assert len(notifications) == 1
    assert notifications[0]["title"] == "You’re next in line"


def test_openai_analysis_is_used_when_configured():
    payload = {
        "summary": "Student needs help finding a bug.",
        "tags": ["debugging"],
        "estimatedHelpMinutes": 9,
        "confidence": "high",
    }
    response = SimpleNamespace(output_text=json.dumps(payload))
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: response))
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch.object(
        ai_service, "OpenAI", return_value=client
    ):
        result = ai_service.analyze_question("CS 101", "Debugging help", "My loop fails")

    assert result == {**payload, "source": "openai"}
