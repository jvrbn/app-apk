"""Submission history screen, including the offline queue."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

from db.database import STATUS_FAILED, STATUS_PENDING, STATUS_SYNCED

STATUS_LABELS = {
    STATUS_SYNCED: ("Sent", (0.13, 0.55, 0.24, 1)),
    STATUS_PENDING: ("Waiting to sync", (0.75, 0.5, 0.05, 1)),
    STATUS_FAILED: ("Rejected", (0.85, 0.2, 0.2, 1)),
}


def format_visit(visit):
    """Return the multi-line text shown for one visit in the history list."""
    status_text = STATUS_LABELS.get(visit["status"], (visit["status"], None))[0]
    lines = [
        "{} - {}".format(visit["customer_name"], visit["location"]),
        "{}  |  {}".format(visit["visit_datetime"], status_text),
    ]
    if visit.get("issues"):
        lines.append("Issues: {}".format(visit["issues"]))
    if visit.get("error"):
        lines.append("Last error: {}".format(visit["error"]))
    return "\n".join(lines)


class HistoryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build()

    @property
    def app(self):
        from kivy.app import App

        return App.get_running_app()

    def _build(self):
        root = BoxLayout(orientation="vertical")

        header = BoxLayout(size_hint_y=None, height=dp(48), padding=(dp(8), 0), spacing=dp(8))
        back_button = Button(text="< Form", size_hint_x=None, width=dp(100))
        back_button.bind(on_release=lambda *_a: self.app.go_to("form"))
        header.add_widget(back_button)
        header.add_widget(Label(text="History"))
        self.sync_button = Button(text="Sync now", size_hint_x=None, width=dp(110))
        self.sync_button.bind(on_release=lambda *_a: self.sync())
        header.add_widget(self.sync_button)
        root.add_widget(header)

        self.status_label = Label(
            text="",
            size_hint_y=None,
            height=dp(32),
            halign="center",
            valign="middle",
        )
        self.status_label.bind(
            width=lambda inst, value: setattr(inst, "text_size", (value, None))
        )
        root.add_widget(self.status_label)

        scroll = ScrollView(do_scroll_x=False)
        self.list_layout = BoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(8),
            size_hint_y=None,
        )
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        self.add_widget(root)

    # -- helpers ----------------------------------------------------------
    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self):
        self.list_layout.clear_widgets()
        visits = self.app.db.recent_visits()
        if not visits:
            self.list_layout.add_widget(
                Label(text="No visits recorded yet.", size_hint_y=None, height=dp(48))
            )
            return
        for visit in visits:
            color = STATUS_LABELS.get(visit["status"], (None, (0.2, 0.2, 0.2, 1)))[1]
            label = Label(
                text=format_visit(visit),
                size_hint_y=None,
                halign="left",
                valign="top",
                color=color,
            )
            label.bind(
                width=lambda inst, value: setattr(inst, "text_size", (value, None)),
                texture_size=lambda inst, value: setattr(inst, "height", value[1] + dp(12)),
            )
            self.list_layout.add_widget(label)

    def _set_busy(self, busy):
        self.sync_button.disabled = busy
        self.sync_button.text = "Syncing..." if busy else "Sync now"

    # -- actions ----------------------------------------------------------
    def sync(self):
        pending = self.app.db.pending_count()
        if not pending:
            self.status_label.text = "Nothing waiting to sync."
            return
        self._set_busy(True)
        self.status_label.text = "Sending {} queued visit(s)...".format(pending)
        self.app.sync_pending(self._on_result, self._on_error)

    def _on_result(self, result):
        self._set_busy(False)
        self.status_label.text = "Sent {}, still queued {}.".format(
            result.get("sent", 0), result.get("remaining", 0)
        )
        self.refresh()

    def _on_error(self, error):
        self._set_busy(False)
        self.status_label.text = "Sync failed: {}".format(error)
        self.refresh()
