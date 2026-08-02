"""Round-trip persistence tests for screensaver_app.settings.Settings."""

from __future__ import annotations

import pytest


def test_defaults(settings_factory):
    """A freshly created Settings instance reads back the schema's declared defaults."""
    settings = settings_factory()
    assert settings.idle_timeout_seconds == 300
    assert settings.selected_mode == "blank"
    assert settings.lock_on_activate is False
    assert settings.disable_on_battery is False
    assert settings.disable_when_inhibited is True
    assert settings.clock_format == "24h"
    assert settings.slideshow_transition == "fade"
    assert settings.launch_at_login is False


def test_round_trip_int(settings_factory):
    """An int property written through Settings reads back unchanged."""
    settings = settings_factory()
    settings.idle_timeout_seconds = 120
    assert settings.idle_timeout_seconds == 120


def test_round_trip_bool(settings_factory):
    """A bool property written through Settings reads back unchanged, in
    both directions."""
    settings = settings_factory()
    settings.lock_on_activate = True
    assert settings.lock_on_activate is True
    settings.lock_on_activate = False
    assert settings.lock_on_activate is False


@pytest.mark.parametrize("mode", ["blank", "clock", "slideshow", "shader", "lines"])
def test_round_trip_selected_mode(settings_factory, mode):
    """Every valid mode id round-trips through the selected-mode property."""
    settings = settings_factory()
    settings.selected_mode = mode
    assert settings.selected_mode == mode


def test_selected_mode_rejects_unknown_value(settings_factory):
    """Setting an unrecognized mode id raises ValueError instead of
    silently writing an invalid value."""
    settings = settings_factory()
    with pytest.raises(ValueError):
        settings.selected_mode = "not-a-real-mode"


def test_idle_timeout_rejects_too_small_value(settings_factory):
    """Setting an idle timeout below the minimum raises ValueError."""
    settings = settings_factory()
    with pytest.raises(ValueError):
        settings.idle_timeout_seconds = 0


def test_clock_format_rejects_unknown_value(settings_factory):
    """Setting an unrecognized clock format raises ValueError."""
    settings = settings_factory()
    with pytest.raises(ValueError):
        settings.clock_format = "36h"


def test_slideshow_directory_falls_back_when_unset(settings_factory):
    """Slideshow directory defaults to a non-empty (XDG Pictures) path when
    unset, and round-trips once explicitly set."""
    settings = settings_factory()
    assert settings.slideshow_directory != ""
    settings.slideshow_directory = "/tmp/my-photos"
    assert settings.slideshow_directory == "/tmp/my-photos"


def test_persists_across_instances_sharing_a_backend(settings_factory, compiled_schema_source):
    """Two independent Settings instances over the same backend see each
    other's writes, the way separate app processes share dconf."""
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    from screensaver_app.settings import Settings

    backend = Gio.memory_settings_backend_new()
    first = Settings(backend=backend, schema_source=compiled_schema_source)
    first.idle_timeout_seconds = 42
    first.selected_mode = "shader"

    second = Settings(backend=backend, schema_source=compiled_schema_source)
    assert second.idle_timeout_seconds == 42
    assert second.selected_mode == "shader"


def test_change_signal_fires_on_write(settings_factory):
    """Writing a property fires the GSettings "changed" signal for that
    key, once the GLib main context gets a chance to dispatch it."""
    import gi

    gi.require_version("GLib", "2.0")
    from gi.repository import GLib

    settings = settings_factory()
    seen: list[str] = []
    settings.connect_changed(seen.append)
    settings.idle_timeout_seconds = 99

    context = GLib.MainContext.default()
    for _ in range(20):
        if "idle-timeout-seconds" in seen:
            break
        context.iteration(False)
    assert "idle-timeout-seconds" in seen
