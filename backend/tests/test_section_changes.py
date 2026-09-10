"""Section change notices retain useful, human-readable before/after values."""
import unittest
from copy import deepcopy
from unittest.mock import patch

from app.services import db_service


class SectionChangeTests(unittest.TestCase):
    def setUp(self):
        self.section = {
            "id": "section-test", "date": "2026-09-08", "startTime": "10:00",
            "endTime": "11:00", "location": "Room 204", "zoomLink": "",
        }
        self.patches = [
            patch.object(db_service, "section_by_id", side_effect=lambda _: deepcopy(self.section)),
            patch.object(db_service, "_section_expiry", return_value=None),
            patch.object(db_service, "sections_collection"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        db_service.sections_collection.update_one.side_effect = self.apply_update

    def apply_update(self, query, update):
        self.section.update(update["$set"])

    def test_records_changed_fields_and_cleared_values(self):
        result = db_service.update_section("section-test", {
            "startTime": "10:30", "location": "", "endTime": "11:00",
            "highlightChange": True,
        })
        self.assertEqual(result["changes"], [
            {"field": "startTime", "label": "Start time", "before": "10:00", "after": "10:30"},
            {"field": "location", "label": "Location", "before": "Room 204", "after": ""},
        ])
        self.assertIn("Location: Room 204 → Not set", result["changeNotice"])
        self.assertTrue(result["changeHighlighted"])

    def test_noop_and_save_preserve_previous_notice(self):
        db_service.update_section("section-test", {"location": "Library", "highlightChange": True})
        previous = deepcopy(self.section)
        for updates in ({"location": "Library", "highlightChange": True},
                        {"location": "Library", "highlightChange": False}, {"saved": True}):
            result = db_service.update_section("section-test", updates)
            for key in ("changes", "changeNotice", "changedAt", "changeHighlighted"):
                self.assertEqual(result[key], previous[key])

    def test_unhighlighted_edit_clears_stale_details(self):
        db_service.update_section("section-test", {"location": "Library", "highlightChange": True})
        result = db_service.update_section("section-test", {"location": "Lab", "highlightChange": False})
        self.assertFalse(result["changeHighlighted"])
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["changeNotice"], "")

    def test_cancellation_is_described(self):
        self.section["status"] = "scheduled"
        result = db_service.update_section("section-test", {"status": "cancelled", "highlightChange": True})
        self.assertIn("Status: scheduled → cancelled", result["changeNotice"])


if __name__ == "__main__":
    unittest.main()
