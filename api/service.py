"""Glue between the local database and the web service.

The service is deliberately free of Kivy imports so it can be unit tested and
reused: screens call it through the app and receive plain dictionaries.
"""

from db.database import visit_payload

from .client import ApiError, AuthError, NetworkError


class VisitService:
    def __init__(self, db, api):
        self.db = db
        self.api = api

    def login(self, username, password):
        token = self.api.login(username, password)
        self.db.set_setting("token", token)
        self.db.set_setting("username", username)
        return token

    def restore_session(self):
        """Reload a previously stored token. Returns True when signed in."""
        token = self.db.get_setting("token")
        if token:
            self.api.set_token(token)
            return True
        return False

    def logout(self):
        self.api.clear_token()
        self.db.delete_setting("token")

    def submit_visit(self, visit):
        """Store a visit locally and try to send it right away.

        Returns a dict with ``visit_id``, ``synced`` and, when the visit could
        not be sent, a ``message`` explaining why it stayed in the queue.
        """
        visit_id = self.db.add_visit(visit)
        stored = self.db.get_visit(visit_id)
        try:
            response = self.api.submit_visit(visit_payload(stored))
        except NetworkError as exc:
            # Offline or transient server problem: keep it queued for later.
            self.db.mark_pending(visit_id, error=str(exc))
            return {"visit_id": visit_id, "synced": False, "message": str(exc)}
        except AuthError as exc:
            self.db.mark_pending(visit_id, error=str(exc))
            return {
                "visit_id": visit_id,
                "synced": False,
                "message": str(exc),
                "auth_error": True,
            }
        except ApiError as exc:
            self.db.mark_failed(visit_id, exc)
            return {"visit_id": visit_id, "synced": False, "message": str(exc)}

        self.db.mark_synced(visit_id, remote_id=self._remote_id(response))
        return {"visit_id": visit_id, "synced": True}

    def sync_pending(self, limit=50):
        """Try to send every queued visit. Returns a summary dict."""
        sent = 0
        rejected = 0
        message = None
        for visit in self.db.pending_visits(limit=limit):
            try:
                response = self.api.submit_visit(visit_payload(visit))
            except NetworkError as exc:
                # Still offline: stop early, the remaining visits stay queued.
                message = str(exc)
                self.db.mark_pending(visit["id"], error=message)
                break
            except AuthError as exc:
                message = str(exc)
                self.db.mark_pending(visit["id"], error=message)
                break
            except ApiError as exc:
                rejected += 1
                self.db.mark_failed(visit["id"], exc)
                continue
            self.db.mark_synced(visit["id"], remote_id=self._remote_id(response))
            sent += 1

        return {
            "sent": sent,
            "rejected": rejected,
            "remaining": self.db.pending_count(),
            "message": message,
        }

    @staticmethod
    def _remote_id(response):
        if isinstance(response, dict):
            value = response.get("id") or response.get("visit_id")
            return str(value) if value is not None else None
        return None
