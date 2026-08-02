"""Idle-timeout crossing logic for IdleMonitor, with the X11/Wayland backends mocked out.

These tests never open a real X display or Wayland connection -- they call
IdleMonitor's internal event handlers directly (``_on_x11_idle_ms``,
``_on_wayland_idled``/``_on_wayland_resumed``) the same way the real
backends would, and stub out ``_should_activate`` / ``_inhibit_watcher`` to
isolate the hysteresis logic from D-Bus and power-state lookups.
"""

from __future__ import annotations

from screensaver_app.idle_detector import IdleMonitor


class _FakeSettings:
    """Minimal stand-in for :class:`screensaver_app.settings.Settings`,
    exposing just the attributes/methods IdleMonitor reads."""

    def __init__(self, idle_timeout_seconds: int = 300) -> None:
        self.idle_timeout_seconds = idle_timeout_seconds
        self.disable_when_inhibited = True
        self.disable_on_battery = False

    def connect_changed(self, _callback):
        """No-op stand-in for Settings.connect_changed; returns a fake handler id."""
        return 0

    def disconnect(self, _handler_id):
        """No-op stand-in for Settings.disconnect."""
        pass


def _monitor(idle_timeout_seconds: int = 10) -> IdleMonitor:
    """Build an ``IdleMonitor`` with fake settings and no real backend
    started, ready to have its internal event handlers called directly."""
    monitor = IdleMonitor(_FakeSettings(idle_timeout_seconds))
    monitor._timeout_seconds = idle_timeout_seconds
    return monitor


def test_x11_idle_fires_once_at_threshold():
    """Crossing the timeout emits "idle" exactly once, staying idle doesn't
    refire it, and dropping back below the timeout emits "active"."""
    monitor = _monitor(idle_timeout_seconds=10)
    monitor._should_activate = lambda: True

    fired = []
    monitor.connect("idle", lambda _m, seconds: fired.append(("idle", seconds)))
    monitor.connect("active", lambda _m: fired.append(("active", None)))

    monitor._on_x11_idle_ms(5_000)  # below threshold
    assert fired == []

    monitor._on_x11_idle_ms(10_000)  # crosses threshold
    assert fired == [("idle", 10.0)]

    monitor._on_x11_idle_ms(15_000)  # still idle -- must not refire
    assert fired == [("idle", 10.0)]

    monitor._on_x11_idle_ms(200)  # user active again
    assert fired == [("idle", 10.0), ("active", None)]


def test_x11_idle_suppressed_when_should_not_activate():
    """No "idle" signal fires when ``_should_activate`` returns False, even
    past the timeout."""
    monitor = _monitor(idle_timeout_seconds=5)
    monitor._should_activate = lambda: False

    fired = []
    monitor.connect("idle", lambda _m, seconds: fired.append(seconds))
    monitor._on_x11_idle_ms(10_000)
    assert fired == []


def test_wayland_idled_and_resumed_events():
    """The compositor's ``idled``/``resumed`` callbacks map straight to
    "idle"/"active" signals."""
    monitor = _monitor(idle_timeout_seconds=30)
    monitor._should_activate = lambda: True

    fired = []
    monitor.connect("idle", lambda _m, seconds: fired.append(("idle", seconds)))
    monitor.connect("active", lambda _m: fired.append(("active", None)))

    monitor._on_wayland_idled()
    assert fired == [("idle", 30.0)]

    monitor._on_wayland_resumed()
    assert fired == [("idle", 30.0), ("active", None)]


def test_wayland_idled_suppressed_by_should_activate():
    """No "idle" signal fires from the Wayland path either when
    ``_should_activate`` returns False."""
    monitor = _monitor(idle_timeout_seconds=30)
    monitor._should_activate = lambda: False

    fired = []
    monitor.connect("idle", lambda _m, seconds: fired.append(seconds))
    monitor._on_wayland_idled()
    assert fired == []


def test_should_activate_respects_inhibit_flag():
    """``_should_activate`` returns False while inhibited, True once the
    inhibit is released."""
    monitor = _monitor()

    class _FakeInhibitWatcher:
        """Stand-in exposing just the ``is_inhibited`` flag IdleMonitor reads."""

        is_inhibited = True

    monitor._inhibit_watcher = _FakeInhibitWatcher()
    assert monitor._should_activate() is False

    monitor._inhibit_watcher.is_inhibited = False
    assert monitor._should_activate() is True


def test_should_activate_respects_battery_setting(monkeypatch):
    """``_should_activate`` returns False on battery when the preference is
    set, True again once ``_is_on_battery`` reports AC power."""
    monitor = _monitor()
    monitor._settings.disable_on_battery = True

    monkeypatch.setattr("screensaver_app.idle_detector._is_on_battery", lambda: True)
    assert monitor._should_activate() is False

    monkeypatch.setattr("screensaver_app.idle_detector._is_on_battery", lambda: False)
    assert monitor._should_activate() is True


def test_settings_change_updates_wayland_backend_timeout():
    """Changing the idle-timeout-seconds GSettings key calls
    ``update_timeout`` on an active Wayland backend with the new value."""
    from screensaver_app.idle_detector import _WaylandIdleBackend

    monitor = _monitor(idle_timeout_seconds=60)
    # __new__ skips _WaylandIdleBackend.__init__ (which would try to import
    # pywayland) while still producing a genuine isinstance() match, so the
    # isinstance check inside _on_settings_changed exercises real code.
    backend = _WaylandIdleBackend.__new__(_WaylandIdleBackend)
    calls: list[int] = []
    backend.update_timeout = calls.append
    monitor._backend = backend

    monitor._settings.idle_timeout_seconds = 120
    monitor._on_settings_changed("idle-timeout-seconds")

    assert calls == [120]
