"""Solid black screen. No timers, no redraws beyond the initial paint."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from screensaver_app.modes import ScreensaverMode

_CSS = b"""
.screensaver-blank { background-color: #000000; }
"""


class BlankMode(ScreensaverMode):
    """The simplest mode: paint the container solid black and do nothing else."""

    mode_id = "blank"

    def render(self, widget: Gtk.Widget) -> None:
        """Apply the solid-black CSS class to ``widget``. No timers, no
        further updates -- ``on_start``/``on_stop`` are the inherited no-ops."""
        widget.add_css_class("screensaver-blank")
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
