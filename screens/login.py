"""Login screen: authenticates the employee against the web service."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from api.client import ApiError

ERROR_COLOR = (0.85, 0.2, 0.2, 1)
INFO_COLOR = (0.2, 0.2, 0.2, 1)


class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build()

    def _build(self):
        root = ScrollView(do_scroll_x=False)
        layout = BoxLayout(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(12),
            size_hint_y=None,
        )
        layout.bind(minimum_height=layout.setter("height"))

        layout.add_widget(
            Label(
                text="Customer Visits",
                font_size=dp(26),
                size_hint_y=None,
                height=dp(56),
            )
        )
        layout.add_widget(
            Label(
                text="Sign in with your employee account",
                size_hint_y=None,
                height=dp(28),
                color=INFO_COLOR,
            )
        )

        self.server_input = TextInput(
            hint_text="Server URL (https://example.com/api)",
            multiline=False,
            write_tab=False,
            size_hint_y=None,
            height=dp(44),
        )
        self.username_input = TextInput(
            hint_text="Username",
            multiline=False,
            write_tab=False,
            size_hint_y=None,
            height=dp(44),
        )
        self.password_input = TextInput(
            hint_text="Password",
            multiline=False,
            write_tab=False,
            size_hint_y=None,
            height=dp(44),
        )
        self.password_input.password = True
        self.password_input.bind(on_text_validate=lambda *_a: self.login())

        layout.add_widget(self.server_input)
        layout.add_widget(self.username_input)
        layout.add_widget(self.password_input)

        self.login_button = Button(
            text="Sign in", size_hint_y=None, height=dp(48)
        )
        self.login_button.bind(on_release=lambda *_a: self.login())
        layout.add_widget(self.login_button)

        self.status_label = Label(
            text="",
            size_hint_y=None,
            height=dp(60),
            halign="center",
            valign="middle",
            color=INFO_COLOR,
        )
        self.status_label.bind(width=lambda inst, value: setattr(inst, "text_size", (value, None)))
        layout.add_widget(self.status_label)

        root.add_widget(layout)
        self.add_widget(root)

    # -- helpers ----------------------------------------------------------
    def on_pre_enter(self, *args):
        self.password_input.text = ""
        self.server_input.text = self.app.api.base_url
        self.username_input.text = self.app.db.get_setting("username", "")
        self._set_status("")
        self._set_busy(False)

    @property
    def app(self):
        from kivy.app import App

        return App.get_running_app()

    def _set_status(self, message, error=False):
        self.status_label.text = message
        self.status_label.color = ERROR_COLOR if error else INFO_COLOR

    def _set_busy(self, busy):
        self.login_button.disabled = busy
        self.login_button.text = "Signing in..." if busy else "Sign in"

    # -- actions ----------------------------------------------------------
    def login(self):
        username = self.username_input.text.strip()
        password = self.password_input.text
        server = self.server_input.text.strip()

        if not username or not password:
            self._set_status("Enter your username and password.", error=True)
            return
        if server and not server.startswith(("http://", "https://")):
            self._set_status("The server URL must start with http:// or https://", error=True)
            return

        if server:
            self.app.set_server_url(server)
        self._set_busy(True)
        self._set_status("Contacting the server...")
        self.app.login(username, password, self._on_success, self._on_error)

    def _on_success(self, _token):
        self._set_busy(False)
        self._set_status("")
        self.password_input.text = ""
        self.app.go_to("form")

    def _on_error(self, error):
        self._set_busy(False)
        message = str(error) if isinstance(error, ApiError) else "Unexpected error: {}".format(error)
        self._set_status(message, error=True)
