"""Session idle detection, unified across X11 and Wayland.

``IdleMonitor`` is the single entry point the rest of the app talks to. It
picks a backend based on ``XDG_SESSION_TYPE`` at start-up:

* X11 -- polls ``XScreenSaverQueryInfo`` (via python-xlib) at most once a
  second, per the project's no-busy-polling rule.
* Wayland -- binds the compositor's ``ext-idle-notify-v1`` global and reacts
  to ``idled``/``resumed`` events pushed by the compositor. No polling at
  all once the notification object is set up.

Either backend can fail to initialize (missing extension, compositor
without the protocol, no X/Wayland connection at all under a headless or
otherwise unsupported session). That is treated as a normal, expected
outcome: the monitor exposes a :class:`BackendState` describing *why*
idle-based activation isn't available, instead of raising. Callers (the
tray icon / settings window) are expected to surface that state to the
user rather than have the app silently never activate.

A second, independent concern lives here too: honoring
``org.freedesktop.ScreenSaver`` inhibit requests (video players,
presentations, games) via :class:`InhibitWatcher`. We host that bus name
ourselves -- if something else already owns it (a full GNOME session
typically does, via gnome-session), inhibit suppression is unavailable and
that too is surfaced as a degraded, non-fatal state rather than a crash.
"""

# Deliberately no `from __future__ import annotations` here: dbus_next's
# @method()/@dbus_property() decorators inspect real function annotations
# at import time (expecting either the literal `None` object or a literal
# D-Bus signature string like "u"), and PEP 563 postponed evaluation turns
# those into plain strings of their source text instead -- which breaks
# dbus_next's parsing. See InhibitWatcher below.

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import gi

gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib, GObject  # noqa: E402

if TYPE_CHECKING:
    from screensaver_app.settings import Settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1


class SessionType(Enum):
    """Which display server this session is running under."""

    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"


class BackendStatus(Enum):
    """Health of an idle/inhibit backend."""

    OK = "ok"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass(frozen=True)
class BackendState:
    """A backend's current status plus a human-readable reason, so callers
    can explain *why* idle detection or inhibit-watching isn't available."""

    status: BackendStatus
    detail: str = ""

    @property
    def ok(self) -> bool:
        """Whether the backend is fully functional."""
        return self.status is BackendStatus.OK


def detect_session_type() -> SessionType:
    """Read ``XDG_SESSION_TYPE`` and map it to a :class:`SessionType`,
    defaulting to :attr:`SessionType.UNKNOWN` (with a warning) for anything
    unrecognized or unset."""
    value = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if value == "x11":
        return SessionType.X11
    if value == "wayland":
        return SessionType.WAYLAND
    logger.warning("Unrecognized or unset XDG_SESSION_TYPE=%r", value)
    return SessionType.UNKNOWN


# --------------------------------------------------------------------------
# X11 backend: MIT-SCREEN-SAVER extension, polled at 1 Hz.
# --------------------------------------------------------------------------


class _X11IdleBackend:
    """Idle detection for X11 sessions via the MIT-SCREEN-SAVER extension,
    polled once a second (X11 has no push-based idle notification)."""

    def __init__(self) -> None:
        """Start out assuming the backend works; :meth:`start` corrects
        ``state`` if python-xlib or the X extension turn out to be missing."""
        self.state = BackendState(BackendStatus.OK)
        self._display = None
        self._root = None
        self._poll_source_id: int | None = None

    def start(self, on_idle_ms) -> bool:
        """Open an X connection, verify the MIT-SCREEN-SAVER extension is
        available, and start a 1 Hz poll that calls ``on_idle_ms(idle_ms)``
        with the server-reported idle time. Returns whether startup
        succeeded; on any failure ``state`` explains why and no poll is
        scheduled."""
        try:
            from Xlib import display as xlib_display
            from Xlib.ext import screensaver as xlib_screensaver  # noqa: F401  (registers the extension methods)
        except ImportError as exc:
            self.state = BackendState(
                BackendStatus.UNSUPPORTED, f"python-xlib is not installed: {exc}"
            )
            return False

        try:
            self._display = xlib_display.Display()
            if not self._display.has_extension("MIT-SCREEN-SAVER"):
                self.state = BackendState(
                    BackendStatus.UNSUPPORTED,
                    "X server does not advertise the MIT-SCREEN-SAVER extension",
                )
                self._display.close()
                self._display = None
                return False
            self._root = self._display.screen().root
        except Exception as exc:  # noqa: BLE001 - any X connection failure degrades gracefully
            self.state = BackendState(BackendStatus.ERROR, f"failed to open X display: {exc}")
            self._display = None
            return False

        def _poll() -> bool:
            """GLib timeout callback: query the server's idle time and
            forward it, or stop the backend (degrading to ERROR) if the
            query itself starts failing."""
            try:
                info = self._root.screensaver_query_info()
            except Exception as exc:  # noqa: BLE001
                logger.warning("X11 idle poll failed, stopping X11 backend: %s", exc)
                self.state = BackendState(BackendStatus.ERROR, str(exc))
                self._poll_source_id = None
                return GLib.SOURCE_REMOVE
            on_idle_ms(info.idle)
            return GLib.SOURCE_CONTINUE

        self._poll_source_id = GLib.timeout_add_seconds(POLL_INTERVAL_SECONDS, _poll)
        self.state = BackendState(BackendStatus.OK)
        return True

    def stop(self) -> None:
        """Cancel the poll timer and close the X connection, if either was
        ever established."""
        if self._poll_source_id is not None:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None
        if self._display is not None:
            try:
                self._display.close()
            except Exception:  # noqa: BLE001
                pass
            self._display = None
            self._root = None


# --------------------------------------------------------------------------
# Wayland backend: ext-idle-notify-v1, event-driven.
#
# pywayland only bundles generated bindings for whatever wayland-protocols
# happened to be installed when its wheel was built, so ext-idle-notify-v1
# (a "staging" protocol) may or may not be present in a given pywayland
# install. We try the bundled module first and treat its absence -- like a
# compositor that doesn't implement the protocol -- as a normal
# "unsupported" outcome rather than a hard dependency failure.
# --------------------------------------------------------------------------


class _WaylandIdleBackend:
    """Idle detection for Wayland sessions via ``ext-idle-notify-v1``: the
    compositor pushes ``idled``/``resumed`` events, so this backend does no
    polling of its own beyond servicing the Wayland connection's fd."""

    def __init__(self) -> None:
        """Start out assuming the backend works; :meth:`start` corrects
        ``state`` if pywayland or the compositor protocol turn out to be
        unavailable."""
        self.state = BackendState(BackendStatus.OK)
        self._display = None
        self._notifier = None
        self._notification = None
        self._seat = None
        self._pump_source_id: int | None = None
        self._on_idled = None
        self._on_resumed = None
        self._timeout_ms = 0

    def start(self, timeout_seconds: int, on_idled, on_resumed) -> bool:
        """Connect to the compositor, bind ``ext_idle_notifier_v1`` and
        ``wl_seat``, create an idle notification for ``timeout_seconds``,
        and start servicing the Wayland connection so ``idled``/``resumed``
        events reach ``on_idled``/``on_resumed``. Returns whether startup
        succeeded; on any failure (missing bindings, unsupported
        compositor, connection error) ``state`` explains why."""
        try:
            from pywayland.client import Display
            from pywayland.protocol.ext_idle_notify_v1 import (  # type: ignore[import-not-found]
                ExtIdleNotifierV1,
            )
            from pywayland.protocol.wayland import WlSeat
        except ImportError as exc:
            self.state = BackendState(
                BackendStatus.UNSUPPORTED,
                "pywayland (or its ext-idle-notify-v1 / wl_seat bindings) is not "
                f"available: {exc}",
            )
            return False

        self._on_idled = on_idled
        self._on_resumed = on_resumed
        self._timeout_ms = max(1, timeout_seconds) * 1000

        try:
            self._display = Display()
            self._display.connect()
            registry = self._display.get_registry()

            found: dict[str, tuple[int, int]] = {}

            def _global_handler(_registry, id_, interface, version):
                """wl_registry "global" handler: record the id/version of
                the two globals this backend needs, ignoring everything
                else the compositor advertises."""
                if interface in ("ext_idle_notifier_v1", "wl_seat"):
                    found[interface] = (id_, version)

            registry.dispatcher["global"] = _global_handler
            self._display.roundtrip()

            if "ext_idle_notifier_v1" not in found or "wl_seat" not in found:
                self.state = BackendState(
                    BackendStatus.UNSUPPORTED,
                    "compositor does not advertise ext_idle_notifier_v1 (or wl_seat)",
                )
                self._teardown()
                return False

            notifier_id, notifier_version = found["ext_idle_notifier_v1"]
            seat_id, seat_version = found["wl_seat"]
            self._notifier = registry.bind(notifier_id, ExtIdleNotifierV1, notifier_version)
            self._seat = registry.bind(seat_id, WlSeat, seat_version)
            self._display.roundtrip()

            self._create_notification()

            # Prefer true event-driven dispatch off the wayland fd when the
            # installed pywayland exposes one; fall back to a 1 Hz pump
            # otherwise. Either way, idle/resume detection itself stays
            # entirely event-driven (the compositor decides when to send
            # `idled`/`resumed`) -- this loop only services the queue.
            fd = None
            for getter in ("get_fd", "fileno"):
                if hasattr(self._display, getter):
                    try:
                        fd = getattr(self._display, getter)()
                    except Exception:  # noqa: BLE001
                        fd = None
                    if fd:
                        break

            if fd:
                self._pump_source_id = GLib.io_add_watch(
                    fd, GLib.IO_IN, lambda *_a: self._pump() or GLib.SOURCE_CONTINUE
                )
            else:
                self._pump_source_id = GLib.timeout_add_seconds(
                    POLL_INTERVAL_SECONDS, lambda: self._pump() or GLib.SOURCE_CONTINUE
                )
        except Exception as exc:  # noqa: BLE001 - never let a Wayland surprise crash the app
            self.state = BackendState(BackendStatus.ERROR, f"ext-idle-notify-v1 setup failed: {exc}")
            self._teardown()
            return False

        self.state = BackendState(BackendStatus.OK)
        return True

    def _create_notification(self) -> None:
        """(Re)create the ``ext_idle_notification_v1`` object for the
        current timeout, wiring its ``idled``/``resumed`` events to the
        callbacks passed into :meth:`start`. Destroys any previous
        notification first, since the protocol has no "update timeout"
        request of its own."""
        if self._notification is not None:
            self._notification.destroy()
        self._notification = self._notifier.get_idle_notification(self._timeout_ms, self._seat)
        self._notification.dispatcher["idled"] = lambda *_a: self._on_idled()
        self._notification.dispatcher["resumed"] = lambda *_a: self._on_resumed()
        self._display.roundtrip()

    def update_timeout(self, timeout_seconds: int) -> None:
        """React to the user changing the idle-timeout preference by
        recreating the idle notification with the new timeout. A no-op if
        the backend isn't in a working state."""
        if self.state.status is not BackendStatus.OK or self._notifier is None:
            return
        self._timeout_ms = max(1, timeout_seconds) * 1000
        try:
            self._create_notification()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to recreate Wayland idle notification on timeout change: %s", exc)

    def _pump(self) -> bool:
        """Service the Wayland connection when its fd is readable (or on
        the 1 Hz fallback timer): read and dispatch queued events, then
        flush any outgoing requests. Returns whether the backend is still
        healthy; on failure it stops itself and degrades to ERROR."""
        try:
            # `dispatch(block=False)` only drains events already queued in
            # memory -- it never reads the socket, so on its own it can't
            # clear the readability condition that woke `GLib.io_add_watch`
            # in the first place. That left the fd permanently "readable"
            # and spun this callback in a tight loop (~100% CPU). `read()`
            # does the actual prepare_read/read_events dance that consumes
            # the socket; the subsequent dispatch() then runs the callbacks
            # for what was just read.
            self._display.read()
            self._display.dispatch(block=False)
            self._display.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wayland event pump failed, stopping Wayland backend: %s", exc)
            self.state = BackendState(BackendStatus.ERROR, str(exc))
            self.stop()
            return False
        return True

    def stop(self) -> None:
        """Cancel the fd watch/poll timer and tear down the Wayland
        connection and protocol objects."""
        if self._pump_source_id is not None:
            GLib.source_remove(self._pump_source_id)
            self._pump_source_id = None
        self._teardown()

    def _teardown(self) -> None:
        """Best-effort destroy/disconnect of the notification and display
        objects, tolerating whichever of them were never created."""
        for obj in (self._notification, self._display):
            if obj is None:
                continue
            try:
                if obj is self._display:
                    obj.disconnect()
                else:
                    obj.destroy()
            except Exception:  # noqa: BLE001
                pass
        self._notification = None
        self._notifier = None
        self._seat = None
        self._display = None


# --------------------------------------------------------------------------
# org.freedesktop.ScreenSaver inhibit watcher
# --------------------------------------------------------------------------


class InhibitWatcher:
    """Hosts org.freedesktop.ScreenSaver so apps can Inhibit()/UnInhibit() us.

    If another service already owns that bus name (common on a stock GNOME
    session, where gnome-session provides it), we cannot also host it --
    inhibit suppression is then reported as unavailable rather than
    guessed at.
    """

    def __init__(self) -> None:
        """Start out assuming the watcher works; :meth:`start` corrects
        ``state`` if the bus name turns out to already be owned."""
        self.state = BackendState(BackendStatus.OK)
        self._cookies: set[int] = set()
        self._next_cookie = 1
        self._bus = None
        self._interface = None
        self._on_change = None

    @property
    def is_inhibited(self) -> bool:
        """Whether at least one caller currently holds an inhibit cookie."""
        return bool(self._cookies)

    def start(self, on_change=None) -> bool:
        """Claim ``org.freedesktop.ScreenSaver`` on the session bus and
        export ``Inhibit``/``UnInhibit``/etc. so other apps (video players,
        presentation software) can suppress activation. ``on_change`` is
        called whenever the inhibited state flips. Returns whether the
        watcher is active; it degrades to UNSUPPORTED (not an error) if
        another service already owns the name."""
        self._on_change = on_change
        try:
            from dbus_next import BusType, RequestNameReply
            from dbus_next.glib import MessageBus
            from dbus_next.service import ServiceInterface, method
        except ImportError as exc:
            self.state = BackendState(BackendStatus.UNSUPPORTED, f"dbus-next is not installed: {exc}")
            return False

        watcher = self

        class _ScreenSaverInterface(ServiceInterface):  # type: ignore[misc]
            """``org.freedesktop.ScreenSaver`` D-Bus interface implementation."""

            def __init__(self) -> None:
                super().__init__("org.freedesktop.ScreenSaver")

            @method()
            def Inhibit(self, application_name: "s", reason_for_inhibit: "s") -> "u":  # noqa: N802
                """Register a new inhibit request and return its cookie,
                which the caller must pass to :meth:`UnInhibit` later."""
                cookie = watcher._next_cookie
                watcher._next_cookie += 1
                watcher._cookies.add(cookie)
                logger.info(
                    "Screensaver inhibited by %r (%r), cookie=%d",
                    application_name,
                    reason_for_inhibit,
                    cookie,
                )
                watcher._notify_change()
                return cookie

            @method()
            def UnInhibit(self, cookie: "u") -> None:  # noqa: N802
                """Release a previously issued inhibit cookie."""
                watcher._cookies.discard(cookie)
                watcher._notify_change()

            @method()
            def GetActive(self) -> "b":  # noqa: N802
                """Whether the screensaver is currently active; always
                reports False since actual activation state isn't wired in."""
                return False

            @method()
            def SimulateUserActivity(self) -> None:  # noqa: N802
                """Standard method on this interface; a no-op here since
                real dismissal already goes through the display manager."""
                return None

        try:
            self._bus = MessageBus(bus_type=BusType.SESSION).connect_sync()
            self._interface = _ScreenSaverInterface()
            self._bus.export("/org/freedesktop/ScreenSaver", self._interface)
            reply = self._bus.request_name_sync("org.freedesktop.ScreenSaver")
            if reply != RequestNameReply.PRIMARY_OWNER:
                self.state = BackendState(
                    BackendStatus.UNSUPPORTED,
                    "org.freedesktop.ScreenSaver is already owned by another service "
                    "(likely the desktop session's own screensaver proxy); "
                    "inhibit requests cannot be observed",
                )
                self._teardown()
                return False
        except Exception as exc:  # noqa: BLE001
            self.state = BackendState(BackendStatus.ERROR, f"failed to host org.freedesktop.ScreenSaver: {exc}")
            self._teardown()
            return False

        self.state = BackendState(BackendStatus.OK)
        return True

    def _notify_change(self) -> None:
        """Invoke the ``on_change`` callback passed to :meth:`start`, if any."""
        if self._on_change is not None:
            self._on_change()

    def stop(self) -> None:
        """Release the bus name and drop all inhibit state."""
        self._teardown()

    def _teardown(self) -> None:
        """Disconnect from the bus (if connected) and reset all state."""
        if self._bus is not None:
            try:
                self._bus.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._bus = None
        self._interface = None
        self._cookies.clear()


def _is_on_battery() -> bool:
    """Best-effort UPower check. Assumes AC power (False) if UPower is unreachable."""
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.UPower",
            "/org/freedesktop/UPower",
            "org.freedesktop.DBus.Properties",
            None,
        )
        result = proxy.call_sync(
            "Get",
            GLib.Variant("(ss)", ("org.freedesktop.UPower", "OnBattery")),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        return bool(result.unpack()[0])
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not query UPower OnBattery, assuming AC power: %s", exc)
        return False


# --------------------------------------------------------------------------
# Unified monitor
# --------------------------------------------------------------------------


class IdleMonitor(GObject.Object):
    """Unified idle-state signal source.

    Signals:
        idle(seconds_idle: float) -- fired once when the idle threshold is
            first crossed (not repeatedly while idle).
        active() -- fired once when user input resumes after an "idle" fire.
        status-changed() -- fired whenever backend/inhibit status changes,
            for the settings window to show a live warning banner.
    """

    __gsignals__ = {
        "idle": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        "active": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "status-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, settings: "Settings") -> None:
        """Detect the session type and set up initial state; the actual
        backend isn't created until :meth:`start` is called."""
        super().__init__()
        self._settings = settings
        self._session_type = detect_session_type()
        self._backend: _X11IdleBackend | _WaylandIdleBackend | None = None
        self._inhibit_watcher = InhibitWatcher()
        self._is_idle_fired = False
        self._timeout_seconds = settings.idle_timeout_seconds
        self._settings_handler_id: int | None = None

    @property
    def session_type(self) -> SessionType:
        """Which display server this session was detected as running under."""
        return self._session_type

    @property
    def backend_state(self) -> BackendState:
        """Current health of the idle-detection backend, for display in
        the settings window."""
        if self._backend is None:
            return BackendState(BackendStatus.UNSUPPORTED, "no idle backend for this session type")
        return self._backend.state

    @property
    def inhibit_state(self) -> BackendState:
        """Current health of the org.freedesktop.ScreenSaver inhibit watcher."""
        return self._inhibit_watcher.state

    @property
    def is_inhibited(self) -> bool:
        """Whether some other application currently holds an inhibit."""
        return self._inhibit_watcher.is_inhibited

    def start(self) -> None:
        """Pick and start the session-appropriate idle backend, start the
        inhibit watcher, and begin reacting to idle-timeout preference
        changes. Safe to call once, after construction."""
        self._settings_handler_id = self._settings.connect_changed(self._on_settings_changed)
        self._timeout_seconds = self._settings.idle_timeout_seconds

        if self._session_type is SessionType.X11:
            self._backend = _X11IdleBackend()
            self._backend.start(self._on_x11_idle_ms)
        elif self._session_type is SessionType.WAYLAND:
            self._backend = _WaylandIdleBackend()
            self._backend.start(self._timeout_seconds, self._on_wayland_idled, self._on_wayland_resumed)
        else:
            self._backend = None
            logger.warning("Idle detection unsupported: unrecognized session type")

        self._inhibit_watcher.start(on_change=lambda: self.emit("status-changed"))
        self.emit("status-changed")

    def stop(self) -> None:
        """Disconnect from settings changes and stop the backend and
        inhibit watcher. Called on application shutdown."""
        if self._settings_handler_id is not None:
            self._settings.disconnect(self._settings_handler_id)
            self._settings_handler_id = None
        if self._backend is not None:
            self._backend.stop()
            self._backend = None
        self._inhibit_watcher.stop()

    def _on_settings_changed(self, key: str) -> None:
        """GSettings "changed" handler: when the idle-timeout preference
        changes, update our cached value and, on Wayland, push the new
        timeout into the compositor's idle notification."""
        if key != "idle-timeout-seconds":
            return
        self._timeout_seconds = self._settings.idle_timeout_seconds
        if isinstance(self._backend, _WaylandIdleBackend):
            self._backend.update_timeout(self._timeout_seconds)

    def _on_x11_idle_ms(self, idle_ms: int) -> None:
        """X11 backend callback: compare the polled idle time against the
        configured timeout and emit "idle"/"active" on threshold crossings
        (with hysteresis via ``_is_idle_fired`` so "idle" fires only once
        per idle period, not on every poll)."""
        idle_seconds = idle_ms / 1000.0
        if idle_seconds >= self._timeout_seconds:
            if not self._is_idle_fired and self._should_activate():
                self._is_idle_fired = True
                self.emit("idle", idle_seconds)
        elif self._is_idle_fired:
            self._is_idle_fired = False
            self.emit("active")

    def _on_wayland_idled(self) -> None:
        """Wayland backend callback for the compositor's ``idled`` event:
        emit "idle" if activation isn't currently suppressed."""
        if self._should_activate():
            self._is_idle_fired = True
            self.emit("idle", float(self._timeout_seconds))

    def _on_wayland_resumed(self) -> None:
        """Wayland backend callback for the compositor's ``resumed`` event:
        emit "active" if we'd previously fired "idle"."""
        if self._is_idle_fired:
            self._is_idle_fired = False
            self.emit("active")

    def _should_activate(self) -> bool:
        """Whether an idle-timeout crossing should actually be allowed to
        activate the screensaver, given the "disable while inhibited" and
        "disable on battery" preferences."""
        if self._settings.disable_when_inhibited and self._inhibit_watcher.is_inhibited:
            logger.debug("Activation suppressed: screensaver is inhibited")
            return False
        if self._settings.disable_on_battery and _is_on_battery():
            logger.debug("Activation suppressed: running on battery")
            return False
        return True
