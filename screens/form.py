"""Customer visit form screen."""

from datetime import datetime

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d")
ERROR_COLOR = (0.85, 0.2, 0.2, 1)
SUCCESS_COLOR = (0.13, 0.55, 0.24, 1)
INFO_COLOR = (0.2, 0.2, 0.2, 1)


def parse_visit_datetime(value):
    """Return an ISO 8601 string for ``value`` or ``None`` when invalid."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            continue
    return None


def validate_visit(fields):
    """Validate raw form input.

    Returns ``(cleaned, errors)`` where ``cleaned`` is a visit dict ready to be
    stored and ``errors`` is a list of human readable messages.
    """
    errors = []
    customer = (fields.get("customer_name") or "").strip()
    location = (fields.get("location") or "").strip()
    raw_datetime = (fields.get("visit_datetime") or "").strip()

    if not customer:
        errors.append("Customer name is required.")
    if not location:
        errors.append("Location is required.")

    visit_datetime = parse_visit_datetime(raw_datetime)
    if visit_datetime is None:
        errors.append("Visit date/time must look like YYYY-MM-DD HH:MM.")

    if errors:
        return None, errors

    return (
        {
            "customer_name": customer,
            "location": location,
            "visit_datetime": visit_datetime,
            "notes": (fields.get("notes") or "").strip(),
            "issues": (fields.get("issues") or "").strip(),
        },
        [],
    )


class FormScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build()

    @property
    def app(self):
        from kivy.app import App

        return App.get_running_app()

    def _text_field(self, hint, height=dp(44), multiline=False):
        return TextInput(
            hint_text=hint,
            multiline=multiline,
            write_tab=False,
            size_hint_y=None,
            height=height,
        )

    def _build(self):
        root = BoxLayout(orientation="vertical")

        header = BoxLayout(size_hint_y=None, height=dp(48), padding=(dp(8), 0), spacing=dp(8))
        self.pending_label = Label(text="", halign="left", valign="middle")
        self.pending_label.bind(
            width=lambda inst, value: setattr(inst, "text_size", (value, None))
        )
        history_button = Button(text="History", size_hint_x=None, width=dp(100))
        history_button.bind(on_release=lambda *_a: self.app.go_to("history"))
        logout_button = Button(text="Sign out", size_hint_x=None, width=dp(100))
        logout_button.bind(on_release=lambda *_a: self.app.logout())
        header.add_widget(self.pending_label)
        header.add_widget(history_button)
        header.add_widget(logout_button)
        root.add_widget(header)

        scroll = ScrollView(do_scroll_x=False)
        form = BoxLayout(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(10),
            size_hint_y=None,
        )
        form.bind(minimum_height=form.setter("height"))

        form.add_widget(
            Label(text="New customer visit", font_size=dp(22), size_hint_y=None, height=dp(40))
        )

        self.customer_input = self._text_field("Customer name *")
        self.location_input = self._text_field("Location *")
        self.datetime_input = self._text_field("Visit date/time (YYYY-MM-DD HH:MM) *")
        self.notes_input = self._text_field("Notes", height=dp(110), multiline=True)
        self.issues_input = self._text_field("Issues reported", height=dp(110), multiline=True)

        for widget in (
            self.customer_input,
            self.location_input,
            self.datetime_input,
            self.notes_input,
            self.issues_input,
        ):
            form.add_widget(widget)

        self.submit_button = Button(text="Submit visit", size_hint_y=None, height=dp(48))
        self.submit_button.bind(on_release=lambda *_a: self.submit())
        form.add_widget(self.submit_button)

        self.status_label = Label(
            text="",
            size_hint_y=None,
            height=dp(70),
            halign="center",
            valign="middle",
            color=INFO_COLOR,
        )
        self.status_label.bind(
            width=lambda inst, value: setattr(inst, "text_size", (value, None))
        )
        form.add_widget(self.status_label)

        scroll.add_widget(form)
        root.add_widget(scroll)
        self.add_widget(root)

    # -- helpers ----------------------------------------------------------
    def on_pre_enter(self, *args):
        if not self.datetime_input.text:
            self.datetime_input.text = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.refresh_pending()

    def refresh_pending(self):
        user = self.app.db.get_setting("username", "")
        pending = self.app.db.pending_count()
        suffix = " - {} waiting to sync".format(pending) if pending else ""
        self.pending_label.text = "Signed in as {}{}".format(user, suffix)

    def _set_status(self, message, level="info"):
        colors = {"info": INFO_COLOR, "error": ERROR_COLOR, "success": SUCCESS_COLOR}
        self.status_label.text = message
        self.status_label.color = colors.get(level, INFO_COLOR)

    def _set_busy(self, busy):
        self.submit_button.disabled = busy
        self.submit_button.text = "Submitting..." if busy else "Submit visit"

    def _clear_form(self):
        self.customer_input.text = ""
        self.location_input.text = ""
        self.notes_input.text = ""
        self.issues_input.text = ""
        self.datetime_input.text = datetime.now().strftime("%Y-%m-%d %H:%M")

    # -- actions ----------------------------------------------------------
    def submit(self):
        cleaned, errors = validate_visit(
            {
                "customer_name": self.customer_input.text,
                "location": self.location_input.text,
                "visit_datetime": self.datetime_input.text,
                "notes": self.notes_input.text,
                "issues": self.issues_input.text,
            }
        )
        if errors:
            self._set_status("\n".join(errors), level="error")
            return

        self._set_busy(True)
        self._set_status("Sending the visit to the server...")
        self.app.submit_visit(cleaned, self._on_result, self._on_error)

    def _on_result(self, result):
        self._set_busy(False)
        self._clear_form()
        self.refresh_pending()
        if result.get("synced"):
            self._set_status("Visit submitted successfully.", level="success")
        else:
            self._set_status(
                "Saved on the device. It will be sent when you are back online.\n({})".format(
                    result.get("message", "no connection")
                ),
                level="info",
            )

    def _on_error(self, error):
        self._set_busy(False)
        self.refresh_pending()
        self._set_status("Could not save the visit: {}".format(error), level="error")
