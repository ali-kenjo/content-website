"""Entry point: Adw.Application, tray icon, and the idle-monitor -> display-window wiring.

Single instance is enforced by ``Gio.ApplicationFlags.HANDLES_COMMAND_LINE``
plus GApplication's built-in D-Bus-backed uniqueness: a second invocation
(e.g. ``screensaver-app --preferences``) is forwarded to the already-running
primary instance's :meth:`do_command_line` instead of starting a new
process, which is also how the app stays controllable with no tray icon at
all (see the ``_TrayIcon`` docstring for why that can happen).
"""

# Deliberately no `from __future__ import annotations` here: dbus_next's
# @method()/@dbus_property() decorators inspect real function annotations
# at import time, and PEP 563 postponed evaluation breaks that (see the
# same note in idle_detector.py, where this was first hit at runtime).
# Every type referenced below is imported directly (no TYPE_CHECKING-only
# forward refs), so dropping the future import needs no other changes.

import contextlib
import logging
import os
import signal
import sys
import time

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from screensaver_app import APPLICATION_ID  # noqa: E402
from screensaver_app.display_window import DisplayManager  # noqa: E402
from screensaver_app.idle_detector import IdleMonitor  # noqa: E402
from screensaver_app.settings import get_default_settings  # noqa: E402
from screensaver_app.settings_window import PreferencesWindow  # noqa: E402

logger = logging.getLogger(__name__)

_DISABLE_DURATION_SECONDS = 3600


class ScreensaverApplication(Adw.Application):
    """The whole app as a single GApplication: owns settings, idle detection,
    the fullscreen display manager, the tray icon, and the GAction set that
    all three of those (plus the CLI) drive the app through."""

    def __init__(self) -> None:
        """Configure the GApplication (single-instance id + CLI handling) and
        declare the ``--preferences``/``--preview`` command-line options.
        Everything else is left uninitialized until :meth:`do_startup` runs."""
        super().__init__(
            application_id=APPLICATION_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self._settings = None
        self._idle_monitor: IdleMonitor | None = None
        self._display_manager: DisplayManager | None = None
        self._tray: _TrayIcon | None = None
        self._preferences_window: PreferencesWindow | None = None
        self._disabled_until = 0.0
        self._held = False

        self.add_main_option(
            "preferences", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Open preferences", None
        )
        self.add_main_option(
            "preview", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Preview the screensaver now", None
        )

    # -- GApplication lifecycle ------------------------------------------------

    def do_startup(self) -> None:
        """GApplication hook run exactly once, in the primary instance only:
        build the settings/idle-monitor/display-manager stack, wire their
        signals together, register the GAction set, install POSIX signal
        handlers, start idle detection, and start the tray icon."""
        Adw.Application.do_startup(self)

        self._settings = get_default_settings()
        self._idle_monitor = IdleMonitor(self._settings)
        self._display_manager = DisplayManager(self, self._settings)
        self._display_manager.connect("dismissed", self._on_dismissed)
        self._idle_monitor.connect("idle", self._on_idle)

        self._install_actions()
        self._install_signal_handlers()

        self._idle_monitor.start()
        logger.info(
            "Idle backend: session=%s status=%s (%s)",
            self._idle_monitor.session_type.value,
            self._idle_monitor.backend_state.status.value,
            self._idle_monitor.backend_state.detail or "ok",
        )
        logger.info(
            "Inhibit watcher: status=%s (%s)",
            self._idle_monitor.inhibit_state.status.value,
            self._idle_monitor.inhibit_state.detail or "ok",
        )

        self._tray = _TrayIcon(self)
        self._tray.start()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        """GApplication hook for every invocation of the executable -- the
        first one (which runs :meth:`do_startup` first) and every later one,
        which GApplication transparently forwards here over D-Bus instead of
        starting a new process. Routes ``--preferences``/``--preview`` to the
        matching GAction, or just activates the app for a bare invocation."""
        options = command_line.get_options_dict()
        if options.contains("preferences"):
            self.activate_action("preferences", None)
        elif options.contains("preview"):
            self.activate_action("preview-now", None)
        else:
            self.activate()
        return 0

    def do_activate(self) -> None:
        """GApplication hook fired on plain activation (no CLI options)."""
        # A pure background app: holding keeps the GLib main loop alive with
        # no window ever needing to be shown just to satisfy GApplication.
        if not self._held:
            self.hold()
            self._held = True

    def do_shutdown(self) -> None:
        """GApplication hook run once on exit: tear down the display
        manager, idle monitor, and tray icon before the process ends."""
        if self._display_manager is not None:
            self._display_manager.deactivate()
        if self._idle_monitor is not None:
            self._idle_monitor.stop()
        if self._tray is not None:
            self._tray.stop()
        Adw.Application.do_shutdown(self)

    # -- setup ------------------------------------------------------------------

    def _install_actions(self) -> None:
        """Register the GAction set (preview-now, preferences,
        disable-for-hour, quit) that both the tray menu and the CLI options
        drive the app through."""
        actions = (
            ("preview-now", self._action_preview_now),
            ("preferences", self._action_preferences),
            ("disable-for-hour", self._action_disable_for_hour),
            ("quit", self._action_quit),
        )
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _install_signal_handlers(self) -> None:
        """Hook SIGTERM/SIGINT into the GLib main loop so the app shuts down
        cleanly (running :meth:`do_shutdown`) instead of being killed."""
        # Python's `signal` module callbacks don't interleave safely with a
        # GLib main loop; GLib.unix_signal_add is the supported way to
        # react to POSIX signals from inside one.
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_shutdown_signal)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._on_shutdown_signal)

    def _on_shutdown_signal(self) -> bool:
        """SIGTERM/SIGINT handler: ask the application to quit."""
        logger.info("Received shutdown signal, quitting")
        self.quit()
        return GLib.SOURCE_REMOVE

    # -- idle monitor wiring ------------------------------------------------

    def _on_idle(self, _monitor: IdleMonitor, seconds_idle: float) -> None:
        """``IdleMonitor`` "idle" signal handler: activate the screensaver,
        unless a "disable for an hour" request is still in effect."""
        if time.monotonic() < self._disabled_until:
            logger.debug("Idle threshold reached but screensaver is temporarily disabled")
            return
        logger.info("Idle threshold reached (%.1fs); activating screensaver", seconds_idle)
        self._display_manager.activate()

    def _on_dismissed(self, _manager: DisplayManager) -> None:
        """``DisplayManager`` "dismissed" signal handler: just logs, since
        the display manager has already torn everything down itself."""
        logger.debug("Screensaver dismissed by user input")

    # -- actions --------------------------------------------------------------

    def _action_preview_now(self, _action: Gio.SimpleAction, _param: None) -> None:
        """"preview-now" GAction handler: show the screensaver immediately,
        used by the tray menu's "Preview now" item and ``--preview``."""
        logger.info("Preview requested (mode=%r)", self._settings.selected_mode)
        activated = self._display_manager.activate()
        if not activated:
            logger.info("Preview request ignored: screensaver is already active")

    def _action_preferences(self, _action: Gio.SimpleAction, _param: None) -> None:
        """"preferences" GAction handler: create the preferences window on
        first use (or reuse the cached one) and bring it to the front."""
        if self._preferences_window is None:
            self._preferences_window = PreferencesWindow(
                self._settings, idle_monitor=self._idle_monitor, application=self
            )
            self._preferences_window.connect("close-request", self._on_preferences_closed)
        self._preferences_window.present()

    def _on_preferences_closed(self, *_args) -> bool:
        """Preferences window "close-request" handler: drop the cached
        reference so the next "preferences" action builds a fresh window."""
        self._preferences_window = None
        return False

    def _action_disable_for_hour(self, _action: Gio.SimpleAction, _param: None) -> None:
        """"disable-for-hour" GAction handler: suppress screensaver
        activation for the next hour (tray menu's "Disable for 1 hour")."""
        self._disabled_until = time.monotonic() + _DISABLE_DURATION_SECONDS
        logger.info("Screensaver activation disabled for %d seconds", _DISABLE_DURATION_SECONDS)

    def _action_quit(self, _action: Gio.SimpleAction, _param: None) -> None:
        """"quit" GAction handler: quit the application."""
        self.quit()


class _TrayIcon:
    """Best-effort StatusNotifierItem + DBusMenu tray icon.

    Deliberately a hand-rolled D-Bus service rather than AppIndicator3/
    libayatana-appindicator: that library's C API expects a GTK3
    ``Gtk.Menu``, and GTK3 cannot be loaded in the same process as GTK4
    (this app) -- the two toolkits' global state conflicts. Implementing
    StatusNotifierItem directly over D-Bus has no GTK-version dependency at
    all, which is the approach GTK4-only apps have converged on.

    If no StatusNotifierWatcher host is registered (e.g. a stock GNOME
    Shell session without the "AppIndicator and KStatusNotifierItem
    Support" extension; COSMIC's own panel registers one natively), the
    icon just never appears anywhere. That is not fatal: the app keeps
    running and stays reachable via ``screensaver-app --preferences`` /
    ``--preview``, which GApplication forwards to this already-running
    instance.
    """

    _MENU_ITEMS = (
        (1, "Preview now", "preview-now"),
        (2, "Preferences", "preferences"),
        (3, "Disable for 1 hour", "disable-for-hour"),
        (4, "Quit", "quit"),
    )

    def __init__(self, app: ScreensaverApplication) -> None:
        """Store the owning application; the actual D-Bus service is only
        created once :meth:`start` is called."""
        self._app = app
        self._bus = None
        self.available = False

    def start(self) -> None:
        """Try to register the tray icon on the session bus. Any failure
        (no StatusNotifierWatcher host, D-Bus unavailable, etc.) is caught
        and downgraded to a warning -- the app must keep running either way."""
        try:
            self._start()
            self.available = True
        except Exception as exc:  # noqa: BLE001 - tray absence must never block the app
            logger.warning("Tray icon unavailable, continuing without one: %s", exc)
            self.available = False

    def stop(self) -> None:
        """Disconnect the tray's D-Bus connection, if one was established."""
        if self._bus is not None:
            with contextlib.suppress(Exception):
                self._bus.disconnect()
            self._bus = None

    def _start(self) -> None:
        """Build and register the StatusNotifierItem + DBusMenu D-Bus
        objects (see the class docstring for why this is hand-rolled
        instead of using AppIndicator3), then request the compositor's
        StatusNotifierWatcher to display the icon."""
        from dbus_next import BusType, Message, MessageType, PropertyAccess, Variant
        from dbus_next.glib import MessageBus
        from dbus_next.service import ServiceInterface, dbus_property, method

        app = self._app
        menu_items = self._MENU_ITEMS

        class _Menu(ServiceInterface):
            """``com.canonical.dbusmenu`` implementation backing the tray
            icon's right-click menu (the four static ``_MENU_ITEMS``)."""

            def __init__(self) -> None:
                super().__init__("com.canonical.dbusmenu")

            @method()
            def GetLayout(self, parent_id: "i", recursion_depth: "i", property_names: "as") -> "u(ia{sv}av)":  # noqa: N802, F821, F722
                """Return the static menu layout a dbusmenu client requests
                before first displaying the menu."""
                children = [
                    Variant(
                        "(ia{sv}av)",
                        [item_id, {"label": Variant("s", label), "enabled": Variant("b", True)}, []],
                    )
                    for item_id, label, _action in menu_items
                ]
                root = [0, {"children-display": Variant("s", "submenu")}, children]
                return [1, root]

            @method()
            def Event(self, item_id: "i", event_id: "s", data: "v", timestamp: "u") -> None:  # noqa: N802, F821
                """Dispatch a menu item click to the matching GAction."""
                if event_id != "clicked":
                    return
                for mid, _label, action_name in menu_items:
                    if mid == item_id:
                        app.activate_action(action_name, None)
                        return

            @method()
            def AboutToShow(self, item_id: "i") -> "b":  # noqa: N802, F821
                """dbusmenu hook called before a submenu is shown; the menu
                is fully static, so there's nothing to prepare."""
                return False

            @dbus_property(access=PropertyAccess.READ)
            def Version(self) -> "u":  # noqa: N802, F821
                """dbusmenu protocol version this implementation speaks."""
                return 3

            @dbus_property(access=PropertyAccess.READ)
            def Status(self) -> "s":  # noqa: N802, F821
                """Static dbusmenu status; the menu is always usable."""
                return "normal"

            @dbus_property(access=PropertyAccess.READ)
            def TextDirection(self) -> "s":  # noqa: N802, F821
                """Static left-to-right text direction for the menu."""
                return "ltr"

        class _Item(ServiceInterface):
            """``org.kde.StatusNotifierItem`` implementation exposing the
            tray icon itself, its metadata, and its click behavior."""

            def __init__(self) -> None:
                super().__init__("org.kde.StatusNotifierItem")

            @dbus_property(access=PropertyAccess.READ)
            def Category(self) -> "s":  # noqa: N802, F821
                """StatusNotifierItem category shown to the host panel."""
                return "ApplicationStatus"

            @dbus_property(access=PropertyAccess.READ)
            def Id(self) -> "s":  # noqa: N802, F821
                """Stable application id used to identify this tray item."""
                return APPLICATION_ID

            @dbus_property(access=PropertyAccess.READ)
            def Title(self) -> "s":  # noqa: N802, F821
                """Human-readable title shown in tooltips/menus."""
                return "Screensaver"

            @dbus_property(access=PropertyAccess.READ)
            def Status(self) -> "s":  # noqa: N802, F821
                """Static "Active" status; the icon is always relevant."""
                return "Active"

            @dbus_property(access=PropertyAccess.READ)
            def IconName(self) -> "s":  # noqa: N802, F821
                """Themed icon name resolved against the installed hicolor
                icon set."""
                return "preferences-desktop-screensaver-symbolic"

            @dbus_property(access=PropertyAccess.READ)
            def IconPixmap(self) -> "a(iiay)":  # noqa: N802, F821
                """Raw pixmap fallback for hosts that can't resolve
                ``IconName``; intentionally empty (see inline note)."""
                # No raw pixmap fallback shipped -- IconName above resolves
                # against the installed hicolor icon, which is sufficient
                # for every compliant host. An empty array is the spec's
                # documented way to say "no pixmap data provided".
                return []

            @dbus_property(access=PropertyAccess.READ)
            def IconThemePath(self) -> "s":  # noqa: N802, F821
                """Extra icon theme search path; empty means "use the
                standard search path" (see inline note)."""
                # Empty string means "use the standard icon theme search
                # path", which is where our icon is actually installed.
                return ""

            @dbus_property(access=PropertyAccess.READ)
            def ItemIsMenu(self) -> "b":  # noqa: N802, F821
                """Tells the host that left-click should open the menu
                rather than call :meth:`Activate` (some hosts ignore this
                and call both; ``Activate`` opens preferences either way)."""
                return True

            @dbus_property(access=PropertyAccess.READ)
            def Menu(self) -> "o":  # noqa: N802, F821
                """Object path of the exported ``_Menu`` instance."""
                return "/MenuBar"

            @method()
            def Activate(self, x: "i", y: "i") -> None:  # noqa: N802, F821
                """Left-click handler: open the preferences window."""
                app.activate_action("preferences", None)

            @method()
            def SecondaryActivate(self, x: "i", y: "i") -> None:  # noqa: N802, F821
                """Middle-click handler: show the screensaver preview."""
                app.activate_action("preview-now", None)

            @method()
            def ContextMenu(self, x: "i", y: "i") -> None:  # noqa: N802, F821
                """Right-click handler; unused since ``Menu`` above already
                gives hosts a menu to display directly."""
                return None

            @method()
            def Scroll(self, delta: "i", orientation: "s") -> None:  # noqa: N802, F821
                """Scroll-wheel handler; this tray icon has nothing to
                scroll through, so it's a no-op."""
                return None

        self._bus = MessageBus(bus_type=BusType.SESSION).connect_sync()
        self._bus.export("/StatusNotifierItem", _Item())
        self._bus.export("/MenuBar", _Menu())

        service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._bus.request_name_sync(service_name)

        register_msg = Message(
            destination="org.kde.StatusNotifierWatcher",
            path="/StatusNotifierWatcher",
            interface="org.kde.StatusNotifierWatcher",
            member="RegisterStatusNotifierItem",
            signature="s",
            body=[service_name],
        )
        reply = self._bus.call_sync(register_msg)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"StatusNotifierWatcher registration failed: {reply.body}")

        logger.info("Tray icon registered as %s", service_name)


def run() -> int:
    """Console-script entry point: configure logging, build the
    application, and hand control to the GApplication/GLib main loop."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = ScreensaverApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(run())
