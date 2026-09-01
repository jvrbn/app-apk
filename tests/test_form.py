"""Validation tests for the visit form.

Importing the screen pulls in Kivy, which needs a display provider, so the whole
module is skipped when Kivy cannot be imported (e.g. on a headless CI runner
without a virtual display). Run them locally with ``xvfb-run -a python -m
unittest discover -s tests`` on Linux.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from screens.form import parse_visit_datetime, validate_visit
    from screens.history import format_visit
except Exception as exc:  # noqa: BLE001 - Kivy/display not available
    KIVY_IMPORT_ERROR = exc
else:
    KIVY_IMPORT_ERROR = None


@unittest.skipIf(KIVY_IMPORT_ERROR, "Kivy is not available: {}".format(KIVY_IMPORT_ERROR))
class FormValidationTest(unittest.TestCase):
    def test_valid_form_is_normalised(self):
        cleaned, errors = validate_visit(
            {
                "customer_name": "  Acme  ",
                "location": "Berlin",
                "visit_datetime": "2026-01-05 10:00",
                "notes": " ok ",
                "issues": "",
            }
        )
        self.assertEqual(errors, [])
        self.assertEqual(cleaned["customer_name"], "Acme")
        self.assertEqual(cleaned["visit_datetime"], "2026-01-05T10:00:00")
        self.assertEqual(cleaned["notes"], "ok")

    def test_required_fields_are_reported(self):
        cleaned, errors = validate_visit(
            {"customer_name": "", "location": "", "visit_datetime": ""}
        )
        self.assertIsNone(cleaned)
        self.assertEqual(len(errors), 3)

    def test_invalid_datetime_is_rejected(self):
        _cleaned, errors = validate_visit(
            {"customer_name": "Acme", "location": "Berlin", "visit_datetime": "yesterday"}
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("date/time", errors[0])

    def test_date_only_is_accepted(self):
        self.assertEqual(parse_visit_datetime("2026-01-05"), "2026-01-05T00:00:00")
        self.assertIsNone(parse_visit_datetime(""))


@unittest.skipIf(KIVY_IMPORT_ERROR, "Kivy is not available: {}".format(KIVY_IMPORT_ERROR))
class HistoryFormattingTest(unittest.TestCase):
    def test_pending_visit_is_labelled(self):
        text = format_visit(
            {
                "customer_name": "Acme",
                "location": "Berlin",
                "visit_datetime": "2026-01-05T10:00:00",
                "status": "pending",
                "issues": "Printer offline",
                "error": None,
            }
        )
        self.assertIn("Acme - Berlin", text)
        self.assertIn("Waiting to sync", text)
        self.assertIn("Printer offline", text)


if __name__ == "__main__":
    unittest.main()
