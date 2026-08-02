"""Large centered digital clock in the style of macOS's modern "Clock" screensaver:
giant ultra-thin digits on a plain black background, with a small, widely
tracked-out date line underneath. Position drifts slightly every few minutes
to avoid burn-in.

Rendered with Cairo/Pango directly (rather than a Gtk.Label + CSS font-size)
so the type size is computed from the actual monitor resolution on every
draw -- a fixed point size looks right on one screen and wrong on the next.
"""

from __future__ import annotations

import datetime as dt
import random
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from screensaver_app.modes import ScreensaverMode

if TYPE_CHECKING:
    from screensaver_app.settings import Settings

_CSS = b"""
.screensaver-clock-bg { background-color: #000000; }
"""

_TICK_INTERVAL_MS = 1000
_DRIFT_INTERVAL_MINUTES = 5
_DRIFT_MAX_PX = 48

# Fonts with an actual Light/Thin weight first, falling back to whatever
# sans-serif is installed -- if none of the named families are present the
# requested weight is silently ignored by fontconfig, which just means a
# regular-weight (not "ultra-thin") render rather than a failure.
_TIME_FONT_FAMILIES = "Ubuntu Light, Inter, Roboto, Noto Sans, sans-serif"
_DATE_FONT_FAMILIES = "Ubuntu, Inter, Roboto, Noto Sans, sans-serif"

_TIME_TARGET_WIDTH_FRACTION = 0.62
_TIME_TARGET_HEIGHT_FRACTION = 0.42
_DATE_TARGET_WIDTH_FRACTION = 0.32
_TIME_DATE_GAP_PX = 22
_BASE_FONT_SIZE_PT = 120

_TIME_COLOR = (0.96, 0.96, 0.96)
_DATE_COLOR = (0.5, 0.5, 0.53)
_DATE_LETTER_SPACING = 3 * Pango.SCALE  # widely tracked-out, like the macOS subtitle


class ClockMode(ScreensaverMode):
    """Digital clock mode: a Cairo/Pango-rendered time + date pair that
    redraws once a minute and drifts to a new random position periodically."""

    mode_id = "clock"

    def __init__(self, settings: Settings) -> None:
        """Set up per-instance drawing/timer state; nothing is drawn or
        scheduled until :meth:`render`/:meth:`on_start` run."""
        super().__init__(settings)
        self._area: Gtk.DrawingArea | None = None
        self._tick_source_id: int | None = None
        self._drift_source_id: int | None = None
        self._drift_x = 0.0
        self._drift_y = 0.0
        self._last_minute: int | None = None

    def render(self, widget: Gtk.Widget) -> None:
        """Apply the black background and add a ``Gtk.DrawingArea`` that
        renders via :meth:`_draw`."""
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        widget.add_css_class("screensaver-clock-bg")

        self._area = Gtk.DrawingArea()
        self._area.set_hexpand(True)
        self._area.set_vexpand(True)
        self._area.set_draw_func(self._draw)
        widget.append(self._area)

    def on_start(self) -> None:
        """Start the once-a-second minute-change check and the periodic
        burn-in-avoidance position drift."""
        self._tick_source_id = GLib.timeout_add(_TICK_INTERVAL_MS, self._on_tick)
        self._drift_source_id = GLib.timeout_add_seconds(
            _DRIFT_INTERVAL_MINUTES * 60, self._on_drift
        )

    def on_stop(self) -> None:
        """Cancel both timers so they don't keep firing after the window
        showing them has been destroyed."""
        if self._tick_source_id is not None:
            GLib.source_remove(self._tick_source_id)
            self._tick_source_id = None
        if self._drift_source_id is not None:
            GLib.source_remove(self._drift_source_id)
            self._drift_source_id = None

    def _on_tick(self) -> bool:
        """Once-a-second timer callback: only actually request a redraw
        when the displayed minute has changed, so idle CPU stays near zero."""
        now = dt.datetime.now()
        if now.minute != self._last_minute and self._area is not None:
            self._area.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _on_drift(self) -> bool:
        """Periodic timer callback: pick a new random on-screen offset for
        the clock and redraw, to avoid burn-in on static displays."""
        self._drift_x = random.uniform(-_DRIFT_MAX_PX, _DRIFT_MAX_PX)
        self._drift_y = random.uniform(-_DRIFT_MAX_PX, _DRIFT_MAX_PX)
        if self._area is not None:
            self._area.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _format_time(self, now: dt.datetime) -> str:
        """Format ``now`` as a time string per the configured clock-format
        preference (24h vs. 12h, with a leading zero stripped in 12h)."""
        if self.settings.clock_format == "12h":
            return now.strftime("%I:%M %p").lstrip("0")
        return now.strftime("%H:%M")

    def _draw(self, _area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        """``Gtk.DrawingArea`` draw function: clear to black, then lay out
        and paint the time and date text, offset by the current drift."""
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        if width <= 0 or height <= 0:
            return

        now = dt.datetime.now()
        self._last_minute = now.minute
        time_text = self._format_time(now)
        date_text = now.strftime("%A, %B %-d").upper()

        cr.save()
        cr.translate(self._drift_x, self._drift_y)

        time_layout, time_w, time_h = self._layout_for(
            cr,
            time_text,
            _TIME_FONT_FAMILIES,
            Pango.Weight.THIN,
            target_width=width * _TIME_TARGET_WIDTH_FRACTION,
            target_height=height * _TIME_TARGET_HEIGHT_FRACTION,
        )
        date_layout, date_w, date_h = self._layout_for(
            cr,
            date_text,
            _DATE_FONT_FAMILIES,
            Pango.Weight.LIGHT,
            target_width=width * _DATE_TARGET_WIDTH_FRACTION,
            letter_spacing=_DATE_LETTER_SPACING,
        )

        total_h = time_h + _TIME_DATE_GAP_PX + date_h
        top = (height - total_h) / 2

        cr.set_source_rgb(*_TIME_COLOR)
        cr.move_to((width - time_w) / 2, top)
        PangoCairo.show_layout(cr, time_layout)

        cr.set_source_rgb(*_DATE_COLOR)
        cr.move_to((width - date_w) / 2, top + time_h + _TIME_DATE_GAP_PX)
        PangoCairo.show_layout(cr, date_layout)

        cr.restore()

    def _layout_for(
        self,
        cr,
        text: str,
        family: str,
        weight: Pango.Weight,
        target_width: float,
        target_height: float | None = None,
        letter_spacing: int | None = None,
    ):
        """Build a Pango layout for ``text`` and scale its font size so the
        rendered text fits ``target_width`` (and ``target_height``, if
        given). Returns ``(layout, pixel_width, pixel_height)``."""
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription()
        desc.set_family(family)
        desc.set_weight(weight)
        desc.set_size(_BASE_FONT_SIZE_PT * Pango.SCALE)
        layout.set_font_description(desc)
        if letter_spacing is not None:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(letter_spacing))
            layout.set_attributes(attrs)
        layout.set_text(text, -1)

        # Font metrics scale ~linearly with point size for a fixed string,
        # so one proportional correction from an arbitrary baseline lands
        # within a percent or two of the actual target -- no need for an
        # iterative search.
        w, h = layout.get_pixel_size()
        if w > 0:
            scale = target_width / w
            if target_height is not None and h > 0:
                scale = min(scale, target_height / h)
            new_size = max(8, int(desc.get_size() / Pango.SCALE * scale))
            desc.set_size(new_size * Pango.SCALE)
            layout.set_font_description(desc)
            w, h = layout.get_pixel_size()
        return layout, w, h
