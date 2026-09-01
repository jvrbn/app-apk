import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import (  # noqa: E402
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SYNCED,
    Database,
    visit_payload,
)


def sample_visit(name="Acme"):
    return {
        "customer_name": name,
        "location": "Berlin",
        "visit_datetime": "2026-01-05T10:00:00",
        "notes": "Quarterly review",
        "issues": "Printer offline",
    }


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.addCleanup(self.db.close)

    def test_add_visit_is_queued_as_pending(self):
        visit_id = self.db.add_visit(sample_visit())
        stored = self.db.get_visit(visit_id)
        self.assertEqual(stored["status"], STATUS_PENDING)
        self.assertEqual(stored["customer_name"], "Acme")
        self.assertEqual(self.db.pending_count(), 1)

    def test_mark_synced_removes_visit_from_queue(self):
        visit_id = self.db.add_visit(sample_visit())
        self.db.mark_synced(visit_id, remote_id="42")
        stored = self.db.get_visit(visit_id)
        self.assertEqual(stored["status"], STATUS_SYNCED)
        self.assertEqual(stored["remote_id"], "42")
        self.assertEqual(self.db.pending_count(), 0)
        self.assertEqual(self.db.pending_visits(), [])

    def test_failed_visits_stay_in_the_queue_for_retry(self):
        visit_id = self.db.add_visit(sample_visit())
        self.db.mark_failed(visit_id, "rejected")
        stored = self.db.get_visit(visit_id)
        self.assertEqual(stored["status"], STATUS_FAILED)
        self.assertEqual(stored["error"], "rejected")
        self.assertEqual(self.db.pending_count(), 1)

    def test_recent_visits_are_newest_first(self):
        self.db.add_visit(sample_visit("First"))
        self.db.add_visit(sample_visit("Second"))
        names = [visit["customer_name"] for visit in self.db.recent_visits()]
        self.assertEqual(names, ["Second", "First"])

    def test_settings_round_trip(self):
        self.assertIsNone(self.db.get_setting("token"))
        self.db.set_setting("token", "abc")
        self.db.set_setting("token", "def")
        self.assertEqual(self.db.get_setting("token"), "def")
        self.db.delete_setting("token")
        self.assertEqual(self.db.get_setting("token", "none"), "none")

    def test_visit_payload_contains_form_fields(self):
        visit_id = self.db.add_visit(sample_visit())
        payload = visit_payload(self.db.get_visit(visit_id))
        self.assertEqual(payload["customer_name"], "Acme")
        self.assertEqual(payload["location"], "Berlin")
        self.assertEqual(payload["issues"], "Printer offline")
        self.assertEqual(payload["client_reference"], str(visit_id))


if __name__ == "__main__":
    unittest.main()
