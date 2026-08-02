"""Fullscreen screensaver windows -- one per connected monitor.

``DisplayManager`` owns the whole lifecycle: creating a borderless,
cursor-hidden, fullscreened window per :class:`Gdk.Monitor`, wiring up
input dismissal, and tearing everything down the moment *any* window sees
qualifying input. Idle state is global (per ``idle_detector.py``), so
dismissal is global too -- input on one monitor closes all of them.

Session locking: GTK4/Wayland removed client-side "always on top" control
(``Gtk.Window.set_keep_above`` is gone), so full-screening each window on
its own monitor is the mechanism -- a fullscreened surface is already
top-of-stack by compositor convention on both X11 and Wayland. If
``lock-on-activate`` is set, the session is locked *before* the windows are
shown (not after dismissal): that is what GNOME actually does, since
locking only after dismissal would briefly expose the unlocked desktop the
moment a monitor wakes.
"""

from __future__ import annotations

import logging
import os
from typing import ClassVar

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from screensaver_app.modes import ScreensaverMode, create_mode  # noqa: E402
from screensaver_app.settings import Settings  # noqa: E402

logger = logging.getLogger(__name__)

_MOTION_JITTER_THRESHOLD_PX = 2.0


def _try_gnome_screensaver_lock() -> bool:
    """Try to lock the session via ``org.gnome.ScreenSaver.Lock()``.
    Returns whether the call succeeded."""
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.gnome.ScreenSaver",
            "/org/gnome/ScreenSaver",
            "org.gnome.ScreenSaver",
            None,
        )
        proxy.call_sync("Lock", None, Gio.DBusCallFlags.NONE, -1, None)
        return True
    except GLib.Error as exc:
        logger.debug("org.gnome.ScreenSaver Lock unavailable: %s", exc)
        return False


def _try_logind_lock() -> bool:
    """Try to lock the session via logind: look up the current process's
    session over ``org.freedesktop.login1``, then call its ``Lock()``.
    Returns whether the call succeeded."""
    try:
        manager = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.login1",
            "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager",
            None,
        )
        result = manager.call_sync(
            "GetSessionByPID", GLib.Variant("(u)", (os.getpid(),)), Gio.DBusCallFlags.NONE, -1, None
        )
        (session_path,) = result.unpack()
        session = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.login1",
            session_path,
            "org.freedesktop.login1.Session",
            None,
        )
        session.call_sync("Lock", None, Gio.DBusCallFlags.NONE, -1, None)
        return True
    except GLib.Error as exc:
        logger.debug("org.freedesktop.login1 session lock unavailable: %s", exc)
        return False


def lock_session() -> None:
    """Best-effort session lock via whichever D-Bus lock interface is available."""
    if _try_gnome_screensaver_lock():
        return
    if _try_logind_lock():
        return
    logger.warning(
        "lock-on-activate is enabled but neither org.gnome.ScreenSaver nor "
        "org.freedesktop.login1 exposed a usable Lock() call"
    )


class DisplayManager(GObject.Object):
    """Shows/hides the fullscreen screensaver window set.

    Signals:
        dismissed() -- fired once when the screensaver is closed by user input.
    """

    __gsignals__: ClassVar = {
        "dismissed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, application: Gtk.Application, settings: Settings) -> None:
        """Store the owning application and settings; no windows exist yet
        until :meth:`activate` is called."""
        super().__init__()
        self._application = application
        self._settings = settings
        self._windows: list[Gtk.Window] = []
        self._modes: list[ScreensaverMode] = []
        self._motion_baselines: dict[Gtk.Window, tuple[float, float]] = {}
        self._active = False

    @property
    def is_active(self) -> bool:
        """Whether the screensaver is currently shown."""
        return self._active

    def activate(self, mode_id: str | None = None) -> bool:
        """Show the screensaver across all monitors. Returns False if already active."""
        if self._active:
            return False

        display = Gdk.Display.get_default()
        if display is None:
            logger.error("No GDK display available; cannot show screensaver")
            return False

        monitors = display.get_monitors()
        monitor_count = monitors.get_n_items()
        if monitor_count == 0:
            logger.warning("No monitors reported by GDK; cannot show screensaver")
            return False

        if self._settings.lock_on_activate:
            lock_session()

        self._active = True
        resolved_mode_id = mode_id or self._settings.selected_mode
        for i in range(monitor_count):
            monitor = monitors.get_item(i)
            self._create_window_for_monitor(monitor, resolved_mode_id)
        return True

    def deactivate(self) -> None:
        """Stop every mode, destroy every fullscreen window, and clear all
        per-activation state. A no-op if the screensaver isn't active."""
        if not self._active:
            return
        self._active = False
        for mode in self._modes:
            try:
                mode.on_stop()
            except Exception:  # one broken mode must not block teardown of the rest
                logger.exception("Error stopping screensaver mode")
        for window in self._windows:
            window.close()
            window.destroy()
        self._windows.clear()
        self._modes.clear()
        self._motion_baselines.clear()

    def _create_window_for_monitor(self, monitor: Gdk.Monitor, mode_id: str) -> None:
        """Build one borderless, cursor-hidden window fullscreened onto
        ``monitor``, render ``mode_id``'s content into it (falling back to
        blank mode if rendering raises), wire up dismiss-on-input
        controllers, show it, and start the mode running."""
        window = Gtk.ApplicationWindow(application=self._application)
        window.set_decorated(False)
        window.set_deletable(False)
        window.set_title("Screensaver")

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        mode = create_mode(mode_id, self._settings)
        try:
            mode.render(container)
        except Exception:  # a mode failing to render must not block the others
            logger.exception("Mode %r failed to render; falling back to blank", mode_id)
            for child in list(container):
                container.remove(child)
            mode = create_mode("blank", self._settings)
            mode.render(container)
        window.set_child(container)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion, window)
        window.add_controller(motion)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key_pressed)
        window.add_controller(key)

        click = Gtk.GestureClick()
        click.connect("pressed", lambda *_a: self._on_dismiss_input())
        window.add_controller(click)

        window.present()
        window.fullscreen_on_monitor(monitor)
        cursor = Gdk.Cursor.new_from_name("none")
        if cursor is not None:
            window.set_cursor(cursor)

        self._windows.append(window)
        self._modes.append(mode)
        mode.on_start()

    def _on_motion(self, _controller: Gtk.EventControllerMotion, x: float, y: float, window: Gtk.Window) -> None:
        """EventControllerMotion "motion" handler: dismiss as soon as the
        pointer has moved more than a tiny noise-floor distance from where
        it was first seen on this window."""
        baseline = self._motion_baselines.get(window)
        if baseline is None:
            # First motion event after showing establishes the baseline --
            # the pointer may already be resting somewhere on screen when
            # the idle timeout fires, and that must not itself count as
            # dismiss-worthy movement.
            self._motion_baselines[window] = (x, y)
            return
        bx, by = baseline
        if ((x - bx) ** 2 + (y - by) ** 2) ** 0.5 > _MOTION_JITTER_THRESHOLD_PX:
            self._on_dismiss_input()

    def _on_key_pressed(self, *_args) -> bool:
        """EventControllerKey "key-pressed" handler: any key dismisses
        immediately, no threshold. Returns True to mark the event handled."""
        self._on_dismiss_input()
        return True

    def _on_dismiss_input(self) -> None:
        """Shared dismiss path for motion/key/click input: tear down the
        screensaver and notify listeners (the application) that it happened."""
        if not self._active:
            return
        self.deactivate()
        self.emit("dismissed")
