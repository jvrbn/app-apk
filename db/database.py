"""SQLite storage for the customer visit app.

Holds two things:

* ``visits`` - every visit created on the device. A visit is ``pending`` while it
  still needs to be sent to the web service, ``synced`` once the server accepted
  it and ``failed`` when the server rejected it. This table doubles as the
  offline queue and as the submission history.
* ``settings`` - small key/value store used for the auth token and the user name.

All methods are safe to call from background threads: a separate connection is
created per thread and every write is committed immediately.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone

STATUS_PENDING = "pending"
STATUS_SYNCED = "synced"
STATUS_FAILED = "failed"

SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    location TEXT NOT NULL,
    visit_datetime TEXT NOT NULL,
    notes TEXT,
    issues TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    remote_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_visits_status ON visits (status);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_db_path():
    """Return the database path, honouring the Android app storage directory."""
    base = os.environ.get("ANDROID_PRIVATE") or os.path.join(
        os.path.expanduser("~"), ".app-apk"
    )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "visits.db")


class Database:
    """Thin wrapper around SQLite with one connection per thread."""

    def __init__(self, path=None):
        self.path = path or default_db_path()
        if self.path != ":memory:":
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            # The database holds the auth token, so keep it owner readable only.
            if not os.path.exists(self.path):
                os.close(os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600))
            else:
                os.chmod(self.path, 0o600)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._connections = []
        self._shared = None
        if self.path == ":memory:":
            # An in-memory database only exists for as long as its connection,
            # so a single shared connection is used (mainly for tests).
            self._shared = self._new_connection()
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    def _new_connection(self):
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        self._connections.append(conn)
        return conn

    def connection(self):
        """Return the connection bound to the calling thread."""
        if self._shared is not None:
            return self._shared
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._new_connection()
            self._local.conn = conn
        return conn

    def close(self):
        """Close every connection opened by the app, including worker threads."""
        with self._lock:
            connections, self._connections = self._connections, []
        for conn in connections:
            conn.close()
        self._shared = None
        self._local = threading.local()

    # -- settings ---------------------------------------------------------
    def set_setting(self, key, value):
        with self._lock:
            conn = self.connection()
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()

    def get_setting(self, key, default=None):
        row = self.connection().execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def delete_setting(self, key):
        with self._lock:
            conn = self.connection()
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()

    # -- visits -----------------------------------------------------------
    def add_visit(self, visit):
        """Insert a visit and return its local id."""
        now = _utcnow()
        with self._lock:
            conn = self.connection()
            cursor = conn.execute(
                "INSERT INTO visits (customer_name, location, visit_datetime, "
                "notes, issues, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    visit["customer_name"],
                    visit["location"],
                    visit["visit_datetime"],
                    visit.get("notes", ""),
                    visit.get("issues", ""),
                    STATUS_PENDING,
                    now,
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def mark_synced(self, visit_id, remote_id=None):
        self._update_status(visit_id, STATUS_SYNCED, error=None, remote_id=remote_id)

    def mark_failed(self, visit_id, error):
        self._update_status(visit_id, STATUS_FAILED, error=str(error))

    def mark_pending(self, visit_id, error=None):
        self._update_status(visit_id, STATUS_PENDING, error=error)

    def _update_status(self, visit_id, status, error=None, remote_id=None):
        with self._lock:
            conn = self.connection()
            conn.execute(
                "UPDATE visits SET status = ?, error = ?, "
                "remote_id = COALESCE(?, remote_id), updated_at = ? WHERE id = ?",
                (status, error, remote_id, _utcnow(), visit_id),
            )
            conn.commit()

    def get_visit(self, visit_id):
        row = self.connection().execute(
            "SELECT * FROM visits WHERE id = ?", (visit_id,)
        ).fetchone()
        return dict(row) if row else None

    def pending_visits(self, limit=50):
        rows = self.connection().execute(
            "SELECT * FROM visits WHERE status IN (?, ?) ORDER BY id ASC LIMIT ?",
            (STATUS_PENDING, STATUS_FAILED, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def recent_visits(self, limit=50):
        rows = self.connection().execute(
            "SELECT * FROM visits ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def pending_count(self):
        row = self.connection().execute(
            "SELECT COUNT(*) AS total FROM visits WHERE status IN (?, ?)",
            (STATUS_PENDING, STATUS_FAILED),
        ).fetchone()
        return row["total"]


def visit_payload(visit):
    """Build the JSON body sent to the web service for a stored visit."""
    return {
        "customer_name": visit["customer_name"],
        "location": visit["location"],
        "visit_datetime": visit["visit_datetime"],
        "notes": visit.get("notes") or "",
        "issues": visit.get("issues") or "",
        "client_reference": str(visit.get("id", "")),
        "created_at": visit.get("created_at"),
    }
