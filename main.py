"""Entry point of the customer visit Kivy app.

Employees sign in once, fill in a visit form at the customer site and the app
takes care of sending it to the web service. When the device is offline the
visit is stored in SQLite and re-sent automatically the next time the app has a
connection.
"""

import os

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, SlideTransition

from api.client import DEFAULT_BASE_URL, ApiClient, run_in_thread
from api.service import VisitService
from db.database import Database
from screens.form import FormScreen
from screens.history import HistoryScreen
from screens.login import LoginScreen

SYNC_INTERVAL_SECONDS = 60


class VisitApp(App):
    title = "Customer Visits"

    def __init__(self, db_path=None, base_url=None, **kwargs):
        super().__init__(**kwargs)
        self.db = Database(db_path)
        self.api = ApiClient(
            base_url or self.db.get_setting("base_url") or DEFAULT_BASE_URL
        )
        self.service = VisitService(self.db, self.api)

    def build(self):
        Window.softinput_mode = "below_target"
        self.manager = ScreenManager(transition=SlideTransition(duration=0.2))
        self.manager.add_widget(LoginScreen(name="login"))
        self.manager.add_widget(FormScreen(name="form"))
        self.manager.add_widget(HistoryScreen(name="history"))
        self.manager.current = "form" if self.service.restore_session() else "login"
        Clock.schedule_interval(self._background_sync, SYNC_INTERVAL_SECONDS)
        return self.manager

    def on_stop(self):
        self.db.close()

    # -- navigation -------------------------------------------------------
    def go_to(self, screen_name):
        self.manager.transition.direction = (
            "left" if screen_name != "login" else "right"
        )
        self.manager.current = screen_name

    # -- session ----------------------------------------------------------
    def set_server_url(self, base_url):
        self.api.base_url = base_url.rstrip("/")
        self.db.set_setting("base_url", self.api.base_url)

    def login(self, username, password, on_success, on_error):
        run_in_thread(
            lambda: self.service.login(username, password), on_success, on_error
        )

    def logout(self):
        self.service.logout()
        self.go_to("login")

    # -- visits -----------------------------------------------------------
    def submit_visit(self, visit, on_success, on_error):
        run_in_thread(lambda: self.service.submit_visit(visit), on_success, on_error)

    def sync_pending(self, on_success=None, on_error=None):
        run_in_thread(self.service.sync_pending, on_success, on_error)

    def _background_sync(self, _dt):
        """Retry queued visits periodically while the employee is signed in."""
        if self.api.token and self.db.pending_count():
            self.sync_pending(self._on_background_sync)

    def _on_background_sync(self, _result):
        form = self.manager.get_screen("form")
        form.refresh_pending()
        if self.manager.current == "history":
            self.manager.get_screen("history").refresh()


def main():
    VisitApp(base_url=os.environ.get("APP_APK_API_URL")).run()


if __name__ == "__main__":
    main()
