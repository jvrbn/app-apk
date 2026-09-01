"""HTTP client for the customer visit web service.

The client only knows about the network; persistence lives in :mod:`db.database`.
Every call raises an :class:`ApiError` subclass on failure so the screens can
show a meaningful message to the employee:

* :class:`NetworkError` - the service could not be reached (offline, timeout).
  The caller should keep the visit queued locally and retry later.
* :class:`AuthError` - the credentials or the stored token are not valid.
* :class:`ApiError` - any other server-side failure.
"""

import os
import threading

import requests

DEFAULT_BASE_URL = os.environ.get("APP_APK_API_URL", "https://example.com/api")
DEFAULT_TIMEOUT = 15


class ApiError(Exception):
    """Base class for every API failure."""


class NetworkError(ApiError):
    """The web service could not be reached; the request may be retried."""


class AuthError(ApiError):
    """Authentication failed or the token expired."""


class ApiClient:
    def __init__(self, base_url=None, timeout=DEFAULT_TIMEOUT, session=None):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self._token = None

    # -- token ------------------------------------------------------------
    @property
    def token(self):
        return self._token

    def set_token(self, token):
        self._token = token

    def clear_token(self):
        self._token = None

    def _headers(self, authenticated=True):
        headers = {"Accept": "application/json"}
        if authenticated and self._token:
            headers["Authorization"] = "Bearer " + self._token
        return headers

    # -- requests ---------------------------------------------------------
    def _request(self, method, path, json=None, authenticated=True):
        url = "{}/{}".format(self.base_url, path.lstrip("/"))
        try:
            response = self.session.request(
                method,
                url,
                json=json,
                headers=self._headers(authenticated),
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise NetworkError("Could not reach the server: {}".format(exc)) from exc

        return self._handle_response(response)

    @staticmethod
    def _parse_body(response):
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {"data": body}

    def _handle_response(self, response):
        body = self._parse_body(response)
        if response.status_code in (401, 403):
            raise AuthError(body.get("message") or "Invalid credentials.")
        if response.status_code >= 500:
            # Server-side problems are transient, so treat them as retryable.
            raise NetworkError(
                "Server error ({}). Please try again later.".format(
                    response.status_code
                )
            )
        if response.status_code >= 400:
            raise ApiError(
                body.get("message")
                or "Request rejected by the server ({}).".format(response.status_code)
            )
        return body

    # -- endpoints --------------------------------------------------------
    def login(self, username, password):
        """Authenticate and store the returned token. Returns the token."""
        body = self._request(
            "POST",
            "/login",
            json={"username": username, "password": password},
            authenticated=False,
        )
        token = body.get("token") or body.get("access_token")
        if not token:
            raise ApiError("The server did not return an authentication token.")
        self.set_token(token)
        return token

    def submit_visit(self, payload):
        """Send one customer visit. Returns the server response body."""
        if not self._token:
            raise AuthError("You are not signed in.")
        return self._request("POST", "/visits", json=payload)


def run_in_thread(func, on_success=None, on_error=None):
    """Run ``func`` off the UI thread and deliver the result on the main thread.

    ``on_success``/``on_error`` are scheduled with Kivy's ``Clock`` when Kivy is
    available so widgets are only touched from the main thread; otherwise they
    are called directly, which keeps the module usable in tests.
    """

    def dispatch(callback, value):
        if callback is None:
            return
        try:
            from kivy.clock import Clock
        except ImportError:
            callback(value)
        else:
            Clock.schedule_once(lambda _dt: callback(value), 0)

    def target():
        try:
            result = func()
        except Exception as exc:  # noqa: BLE001 - surfaced to the user via on_error
            dispatch(on_error, exc)
        else:
            dispatch(on_success, result)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread
