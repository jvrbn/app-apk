import json
import os
import sys
import unittest

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.client import ApiClient, ApiError, AuthError, NetworkError  # noqa: E402
from api.service import VisitService  # noqa: E402
from db.database import STATUS_FAILED, STATUS_PENDING, STATUS_SYNCED, Database  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return json.loads(json.dumps(self._body))


class FakeSession:
    """Records requests and replays a scripted list of responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append(
            {"method": method, "url": url, "json": json, "headers": headers or {}}
        )
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def client_with(responses, base_url="https://example.com/api"):
    session = FakeSession(responses)
    return ApiClient(base_url=base_url, session=session), session


class ApiClientTest(unittest.TestCase):
    def test_login_stores_token_and_posts_credentials(self):
        client, session = client_with([FakeResponse(200, {"token": "t0ken"})])
        token = client.login("employee", "secret")
        self.assertEqual(token, "t0ken")
        self.assertEqual(client.token, "t0ken")
        self.assertEqual(session.calls[0]["url"], "https://example.com/api/login")
        self.assertEqual(session.calls[0]["json"]["username"], "employee")
        self.assertNotIn("Authorization", session.calls[0]["headers"])

    def test_login_without_token_in_response_is_an_error(self):
        client, _ = client_with([FakeResponse(200, {})])
        with self.assertRaises(ApiError):
            client.login("employee", "secret")

    def test_invalid_credentials_raise_auth_error(self):
        client, _ = client_with([FakeResponse(401, {"message": "bad password"})])
        with self.assertRaises(AuthError) as ctx:
            client.login("employee", "secret")
        self.assertIn("bad password", str(ctx.exception))

    def test_connection_problem_raises_network_error(self):
        client, _ = client_with([requests.exceptions.ConnectTimeout("offline")])
        client.set_token("t0ken")
        with self.assertRaises(NetworkError):
            client.submit_visit({"customer_name": "Acme"})

    def test_server_error_is_retryable(self):
        client, _ = client_with([FakeResponse(503, None)])
        client.set_token("t0ken")
        with self.assertRaises(NetworkError):
            client.submit_visit({"customer_name": "Acme"})

    def test_bad_request_raises_api_error(self):
        client, _ = client_with([FakeResponse(422, {"message": "location missing"})])
        client.set_token("t0ken")
        with self.assertRaises(ApiError) as ctx:
            client.submit_visit({"customer_name": "Acme"})
        self.assertIn("location missing", str(ctx.exception))

    def test_submit_requires_authentication(self):
        client, _ = client_with([])
        with self.assertRaises(AuthError):
            client.submit_visit({"customer_name": "Acme"})

    def test_submit_sends_the_token(self):
        client, session = client_with([FakeResponse(201, {"id": 7})])
        client.set_token("t0ken")
        client.submit_visit({"customer_name": "Acme"})
        self.assertEqual(session.calls[0]["headers"]["Authorization"], "Bearer " + "t0ken")


class VisitServiceTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.addCleanup(self.db.close)

    def service_with(self, responses):
        client, session = client_with(responses)
        return VisitService(self.db, client), session

    @staticmethod
    def visit(name="Acme"):
        return {
            "customer_name": name,
            "location": "Berlin",
            "visit_datetime": "2026-01-05T10:00:00",
            "notes": "",
            "issues": "",
        }

    def test_successful_submission_is_marked_as_synced(self):
        service, _ = self.service_with([FakeResponse(201, {"id": 9})])
        service.api.set_token("t0ken")
        result = service.submit_visit(self.visit())
        self.assertTrue(result["synced"])
        stored = self.db.get_visit(result["visit_id"])
        self.assertEqual(stored["status"], STATUS_SYNCED)
        self.assertEqual(stored["remote_id"], "9")

    def test_offline_submission_stays_queued(self):
        service, _ = self.service_with([requests.exceptions.ConnectionError("offline")])
        service.api.set_token("t0ken")
        result = service.submit_visit(self.visit())
        self.assertFalse(result["synced"])
        self.assertEqual(self.db.get_visit(result["visit_id"])["status"], STATUS_PENDING)
        self.assertEqual(self.db.pending_count(), 1)

    def test_rejected_submission_is_marked_failed(self):
        service, _ = self.service_with([FakeResponse(400, {"message": "nope"})])
        service.api.set_token("t0ken")
        result = service.submit_visit(self.visit())
        self.assertFalse(result["synced"])
        self.assertEqual(self.db.get_visit(result["visit_id"])["status"], STATUS_FAILED)

    def test_sync_pending_sends_queued_visits(self):
        service, session = self.service_with(
            [
                requests.exceptions.ConnectionError("offline"),
                requests.exceptions.ConnectionError("offline"),
                FakeResponse(201, {"id": 1}),
                FakeResponse(201, {"id": 2}),
            ]
        )
        service.api.set_token("t0ken")
        service.submit_visit(self.visit("First"))
        service.submit_visit(self.visit("Second"))
        self.assertEqual(self.db.pending_count(), 2)

        summary = service.sync_pending()
        self.assertEqual(summary["sent"], 2)
        self.assertEqual(summary["remaining"], 0)
        self.assertEqual(len(session.calls), 4)

    def test_sync_pending_stops_when_still_offline(self):
        service, session = self.service_with(
            [
                requests.exceptions.ConnectionError("offline"),
                requests.exceptions.ConnectionError("offline"),
                requests.exceptions.ConnectionError("offline"),
            ]
        )
        service.api.set_token("t0ken")
        service.submit_visit(self.visit("First"))
        service.submit_visit(self.visit("Second"))

        summary = service.sync_pending()
        self.assertEqual(summary["sent"], 0)
        self.assertEqual(summary["remaining"], 2)
        # Only the first queued visit is retried before giving up.
        self.assertEqual(len(session.calls), 3)

    def test_login_and_restore_session(self):
        service, _ = self.service_with([FakeResponse(200, {"token": "t0ken"})])
        service.login("employee", "secret")
        self.assertEqual(self.db.get_setting("token"), "t0ken")

        other_client, _ = client_with([])
        other = VisitService(self.db, other_client)
        self.assertTrue(other.restore_session())
        self.assertEqual(other.api.token, "t0ken")

        other.logout()
        self.assertIsNone(self.db.get_setting("token"))
        self.assertIsNone(other.api.token)
        self.assertFalse(other.restore_session())


if __name__ == "__main__":
    unittest.main()
