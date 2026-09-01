# app-apk

A Kivy Android app that lets employees submit a **customer visit form** to your web
service. Visits are stored on the device first, so the app keeps working without a
connection and sends the queued forms as soon as the phone is back online.

## Features

- Login screen with the server URL, username and password; the auth token is stored
  on the device so employees only sign in once.
- Visit form: customer name, location, visit date/time, notes and issues reported,
  with client-side validation.
- Submissions are sent to your web service in a background thread, so the UI never
  freezes; success and error messages are shown on screen.
- Offline support: a visit that cannot be sent stays in a local SQLite queue and is
  retried automatically every minute and from the **Sync now** button.
- History screen listing every visit with its status (sent, waiting to sync, rejected).

## Project layout

```
main.py             Kivy app, ScreenManager wiring and background sync
screens/login.py    Login screen
screens/form.py     Customer visit form (+ validation helpers)
screens/history.py  Submission history and offline queue
api/client.py       HTTP client, error types and the threading helper
api/service.py      Combines the API client with local storage
db/database.py      SQLite schema, offline queue and settings storage
tests/              Unit tests for the database, API client and validation
buildozer.spec      Android packaging configuration
```

## Running on a desktop

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Point the app at your web service (defaults to https://example.com/api)
export APP_APK_API_URL=https://your-service.example.com/api
python main.py
```

The server URL can also be typed on the login screen; it is remembered for the next
start.

## Web service contract

The app expects two JSON endpoints under the configured base URL.

`POST /login`

```json
{ "username": "employee", "password": "secret" }
```

Response: `{ "token": "..." }` (`access_token` is also accepted). A `401`/`403`
response is reported to the employee as invalid credentials.

`POST /visits` with header `Authorization: Bearer <token>`:

```json
{
  "customer_name": "Acme Ltd",
  "location": "Berlin",
  "visit_datetime": "2026-01-05T10:00:00",
  "notes": "Quarterly review",
  "issues": "Printer offline",
  "client_reference": "12",
  "created_at": "2026-01-05T09:58:00+00:00"
}
```

Response: any `2xx`, optionally `{ "id": 42 }` which is stored as the remote id.
`client_reference` is the local row id and can be used to de-duplicate retries.

Error handling:

| Server response          | App behaviour                                        |
| ------------------------ | ---------------------------------------------------- |
| connection error/timeout | visit stays queued, retried automatically            |
| `5xx`                    | treated as temporary, visit stays queued             |
| `401` / `403`            | visit stays queued, employee is asked to sign in again |
| other `4xx`              | visit is marked as rejected and shown in the history |

Use an `https://` endpoint: Android blocks cleartext HTTP by default and the token is
sent on every request.

## Running the tests

```bash
python -m unittest discover -s tests
```

The database and API tests run anywhere. The form/history tests import Kivy, which
needs a display; on a headless Linux machine run them with
`xvfb-run -a python -m unittest discover -s tests` (they are skipped automatically if
Kivy cannot be imported).

## Building the Android APK

Buildozer runs on Linux (or WSL on Windows):

```bash
pip install buildozer cython
buildozer android debug            # produces bin/appapk-0.1.0-debug.apk
buildozer android debug deploy run # install and start on a connected device
```

The first build downloads the Android SDK/NDK and takes a while. Adjust
`package.domain`, `version` and `android.archs` in `buildozer.spec` for your
organisation, and use `buildozer android release` plus your own keystore for a signed
build.

## Data stored on the device

`visits.db` lives in the app's private storage (`ANDROID_PRIVATE`, or `~/.app-apk` on a
desktop), is created with owner-only permissions and holds the queued/sent visits plus
the auth token. Signing out deletes the token.
