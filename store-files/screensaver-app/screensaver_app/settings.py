"""Typed wrapper around the application's GSettings schema.

Provides persistence via ``Gio.Settings`` (the native Linux config store,
backed by dconf) and re-exposes GSettings' native change-notification signal
so other modules can react live to preference edits without polling or
requiring a restart.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

SCHEMA_ID = "com.alikenjo.screensaver"

_VALID_MODES = frozenset({"blank", "clock", "slideshow", "shader", "lines"})
_VALID_CLOCK_FORMATS = frozenset({"24h", "12h"})
_VALID_TRANSITIONS = frozenset({"fade", "slide", "none"})


def _find_dev_schema_dir() -> str | None:
    """Locate the in-tree ``data/`` dir when the schema isn't installed system-wide.

    Lets the app run straight from a source checkout during development
    without requiring `glib-compile-schemas` + install into
    /usr/share/glib-2.0/schemas first. Falls back to None (rely on the
    system's compiled schema search path) once the app is actually packaged.
    """
    here = Path(__file__).resolve().parent
    candidate = here.parent / "data"
    if (candidate / "gschemas.compiled").exists():
        return str(candidate)
    return None


def _get_schema_source() -> Gio.SettingsSchemaSource:
    """Return whichever :class:`Gio.SettingsSchemaSource` actually has our
    schema: the system-wide compiled source if it's installed there, else
    the in-tree dev-compiled ``data/`` directory. Raises if neither has it."""
    default_source = Gio.SettingsSchemaSource.get_default()
    if default_source is not None and default_source.lookup(SCHEMA_ID, True):
        return default_source

    dev_dir = _find_dev_schema_dir()
    if dev_dir is not None:
        return Gio.SettingsSchemaSource.new_from_directory(dev_dir, default_source, False)

    raise RuntimeError(
        f"GSettings schema {SCHEMA_ID!r} is not installed and no compiled dev "
        "schema was found. Run `glib-compile-schemas data/` in the project "
        "root, or install data/*.gschema.xml into "
        "/usr/share/glib-2.0/schemas/ and run glib-compile-schemas there."
    )


def compile_dev_schema(project_root: Path) -> None:
    """Compile the schema in-place under ``project_root/data`` for dev/test use."""
    data_dir = project_root / "data"
    Gio.SettingsSchemaSource.new_from_directory(str(data_dir), None, False)
    # new_from_directory validates but doesn't write gschemas.compiled; that
    # requires the glib-compile-schemas binary, invoked by callers (e.g. a
    # Makefile target or test fixture) rather than at import time.


class Settings:
    """Typed accessor over the app's GSettings schema.

    Every property reads/writes straight through to ``Gio.Settings`` (no
    caching), so multiple ``Settings`` instances in the same process, or
    separate processes entirely, always observe a consistent value. Use
    :meth:`connect_changed` to be notified live when any key changes.
    """

    def __init__(
        self,
        backend: Gio.SettingsBackend | None = None,
        schema_source: Gio.SettingsSchemaSource | None = None,
    ) -> None:
        """Look up the app's schema (from ``schema_source``, or the default
        system/dev lookup) and open a ``Gio.Settings`` instance over it,
        optionally against a non-default ``backend`` (e.g. an in-memory one
        for tests)."""
        schema_source = schema_source if schema_source is not None else _get_schema_source()
        schema = schema_source.lookup(SCHEMA_ID, False)
        if schema is None:
            raise RuntimeError(f"schema {SCHEMA_ID!r} not found in source")
        self._gsettings = Gio.Settings.new_full(schema, backend, None)

    # -- change notification -------------------------------------------------

    def connect_changed(self, callback: Callable[[str], None]) -> int:
        """Invoke ``callback(key)`` whenever any key changes. Returns a handler id."""
        return self._gsettings.connect(
            "changed", lambda _settings, key: callback(key)
        )

    def disconnect(self, handler_id: int) -> None:
        """Disconnect a change-notification handler previously returned by
        :meth:`connect_changed`."""
        self._gsettings.disconnect(handler_id)

    def bind(self, key: str, obj: Any, prop: str, flags: Gio.SettingsBindFlags = Gio.SettingsBindFlags.DEFAULT) -> None:
        """Two-way bind a GSettings key directly to a GObject property (e.g. a Gtk.Switch)."""
        self._gsettings.bind(key, obj, prop, flags)

    def sync(self) -> None:
        """Force any pending writes out to the dconf database immediately."""
        Gio.Settings.sync()

    # -- idle-timeout-seconds --------------------------------------------------

    @property
    def idle_timeout_seconds(self) -> int:
        """Seconds of inactivity before the screensaver activates."""
        return self._gsettings.get_int("idle-timeout-seconds")

    @idle_timeout_seconds.setter
    def idle_timeout_seconds(self, value: int) -> None:
        """Set the idle timeout; rejects values below 5 seconds."""
        if value < 5:
            raise ValueError("idle_timeout_seconds must be >= 5")
        self._gsettings.set_int("idle-timeout-seconds", value)

    # -- selected-mode -----------------------------------------------------

    @property
    def selected_mode(self) -> str:
        """The currently selected screensaver mode id (blank/clock/slideshow/shader/lines)."""
        return self._gsettings.get_string("selected-mode")

    @selected_mode.setter
    def selected_mode(self, value: str) -> None:
        """Set the selected mode; rejects anything outside ``_VALID_MODES``."""
        if value not in _VALID_MODES:
            raise ValueError(f"invalid mode {value!r}, expected one of {sorted(_VALID_MODES)}")
        self._gsettings.set_string("selected-mode", value)

    # -- lock-on-activate ----------------------------------------------------

    @property
    def lock_on_activate(self) -> bool:
        """Whether activating the screensaver should also lock the session."""
        return self._gsettings.get_boolean("lock-on-activate")

    @lock_on_activate.setter
    def lock_on_activate(self, value: bool) -> None:
        """Set whether activation should also lock the session."""
        self._gsettings.set_boolean("lock-on-activate", value)

    # -- disable-on-battery --------------------------------------------------

    @property
    def disable_on_battery(self) -> bool:
        """Whether activation should be suppressed while on battery power."""
        return self._gsettings.get_boolean("disable-on-battery")

    @disable_on_battery.setter
    def disable_on_battery(self, value: bool) -> None:
        """Set whether activation should be suppressed on battery power."""
        self._gsettings.set_boolean("disable-on-battery", value)

    # -- disable-when-inhibited -----------------------------------------------

    @property
    def disable_when_inhibited(self) -> bool:
        """Whether activation should be suppressed while another app holds
        an org.freedesktop.ScreenSaver inhibit (video players, etc.)."""
        return self._gsettings.get_boolean("disable-when-inhibited")

    @disable_when_inhibited.setter
    def disable_when_inhibited(self, value: bool) -> None:
        """Set whether activation should be suppressed while inhibited."""
        self._gsettings.set_boolean("disable-when-inhibited", value)

    # -- slideshow-directory --------------------------------------------------

    @property
    def slideshow_directory(self) -> str:
        """Resolved slideshow directory; falls back to XDG Pictures if unset."""
        raw = self._gsettings.get_string("slideshow-directory")
        if raw:
            return raw
        pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        return pictures or str(Path.home() / "Pictures")

    @slideshow_directory.setter
    def slideshow_directory(self, value: str) -> None:
        """Set the slideshow image directory."""
        self._gsettings.set_string("slideshow-directory", value)

    # -- slideshow-interval-seconds -------------------------------------------

    @property
    def slideshow_interval_seconds(self) -> int:
        """Seconds each slideshow image is shown before advancing."""
        return self._gsettings.get_int("slideshow-interval-seconds")

    @slideshow_interval_seconds.setter
    def slideshow_interval_seconds(self, value: int) -> None:
        """Set the slideshow interval; rejects values below 1 second."""
        if value < 1:
            raise ValueError("slideshow_interval_seconds must be >= 1")
        self._gsettings.set_int("slideshow-interval-seconds", value)

    # -- slideshow-transition -------------------------------------------------

    @property
    def slideshow_transition(self) -> str:
        """The slideshow transition style ("fade", "slide", or "none")."""
        return self._gsettings.get_string("slideshow-transition")

    @slideshow_transition.setter
    def slideshow_transition(self, value: str) -> None:
        """Set the slideshow transition style; rejects anything outside
        ``_VALID_TRANSITIONS``."""
        if value not in _VALID_TRANSITIONS:
            raise ValueError(f"invalid transition {value!r}")
        self._gsettings.set_string("slideshow-transition", value)

    # -- shader-selection ----------------------------------------------------

    @property
    def shader_selection(self) -> str:
        """The selected shader: a built-in name or a path to a custom ``.frag`` file."""
        return self._gsettings.get_string("shader-selection")

    @shader_selection.setter
    def shader_selection(self, value: str) -> None:
        """Set the selected shader (built-in name or custom file path)."""
        self._gsettings.set_string("shader-selection", value)

    # -- clock-format --------------------------------------------------------

    @property
    def clock_format(self) -> str:
        """The clock mode's time format ("24h" or "12h")."""
        return self._gsettings.get_string("clock-format")

    @clock_format.setter
    def clock_format(self, value: str) -> None:
        """Set the clock time format; rejects anything outside
        ``_VALID_CLOCK_FORMATS``."""
        if value not in _VALID_CLOCK_FORMATS:
            raise ValueError(f"invalid clock format {value!r}")
        self._gsettings.set_string("clock-format", value)

    # -- preview-mode ---------------------------------------------------------

    @property
    def preview_mode(self) -> bool:
        """Internal flag used while previewing a mode in the preferences window."""
        return self._gsettings.get_boolean("preview-mode")

    @preview_mode.setter
    def preview_mode(self, value: bool) -> None:
        """Set the preview-mode flag."""
        self._gsettings.set_boolean("preview-mode", value)

    # -- launch-at-login -------------------------------------------------------

    @property
    def launch_at_login(self) -> bool:
        """Whether the app is set to autostart at login."""
        return self._gsettings.get_boolean("launch-at-login")

    @launch_at_login.setter
    def launch_at_login(self, value: bool) -> None:
        """Set whether the app should autostart at login. Note: this only
        stores the preference -- ``autostart.py`` is what actually creates
        or removes the autostart ``.desktop`` file in response to it."""
        self._gsettings.set_boolean("launch-at-login", value)


def get_default_settings() -> Settings:
    """Convenience constructor honoring GSETTINGS_BACKEND for tests (e.g. 'memory')."""
    backend = None
    if os.environ.get("GSETTINGS_BACKEND") == "memory":
        backend = Gio.memory_settings_backend_new()
    return Settings(backend=backend)
