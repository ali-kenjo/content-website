"""Screensaver render modes.

Every mode implements :class:`ScreensaverMode`: a tiny lifecycle plus a
single ``render`` call that populates a container widget handed to it by
``display_window.py``. Modes own their own timers/animations and must stop
them in :meth:`ScreensaverMode.on_stop` -- a display window can be torn down
at any time (user input), so leaked `GLib.timeout_add` sources are a real
way to burn CPU after the screensaver is dismissed.

A fresh mode instance is created per monitor window (see
``create_mode``) so a slideshow crossfade or a shader's shader-toy `iTime`
uniform on one screen never has to coordinate with another.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

if TYPE_CHECKING:
    from screensaver_app.settings import Settings

MODE_IDS = ("blank", "clock", "slideshow", "shader", "lines")


class ScreensaverMode(ABC):
    """Common interface all render modes implement."""

    mode_id: ClassVar[str]

    def __init__(self, settings: Settings) -> None:
        """Store the shared settings object; subclasses read from it in
        ``render``/``on_start`` rather than caching values themselves."""
        self.settings = settings

    @abstractmethod
    def render(self, widget: Gtk.Widget) -> None:
        """Populate ``widget`` (an empty Gtk.Box) with this mode's content."""

    def on_start(self) -> None:  # noqa: B027 - deliberately optional hook, e.g. BlankMode never overrides it
        """Called right after ``render`` when the window becomes visible."""

    def on_stop(self) -> None:  # noqa: B027 - deliberately optional hook, e.g. BlankMode never overrides it
        """Called before the window is destroyed. Stop all timers/animations here."""


def create_mode(mode_id: str, settings: Settings) -> ScreensaverMode:
    """Factory: instantiate a fresh :class:`ScreensaverMode` for ``mode_id``.
    Imports are done lazily inside the function so importing this module
    doesn't pull in every mode's dependencies (e.g. PyOpenGL for the shader
    mode) up front. Raises ValueError for an unknown mode id."""
    from screensaver_app.modes.blank import BlankMode
    from screensaver_app.modes.clock import ClockMode
    from screensaver_app.modes.lines import LinesMode
    from screensaver_app.modes.photo_slideshow import PhotoSlideshowMode
    from screensaver_app.modes.shader import ShaderMode

    modes: dict[str, type[ScreensaverMode]] = {
        "blank": BlankMode,
        "clock": ClockMode,
        "slideshow": PhotoSlideshowMode,
        "shader": ShaderMode,
        "lines": LinesMode,
    }
    try:
        mode_cls = modes[mode_id]
    except KeyError:
        raise ValueError(f"unknown screensaver mode {mode_id!r}, expected one of {MODE_IDS}") from None
    return mode_cls(settings)
