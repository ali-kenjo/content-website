"""Generative screensaver: one or two random straight line segments visible
at a time, each drifting across the screen in its own random direction while
fading in, holding briefly, and fading out, then being replaced by a new one
elsewhere -- in a calm, warm color palette on a dark background.

Unlike a persistent-canvas approach, nothing accumulates: every frame is
redrawn from the small list of currently-live lines (at most two), so the
screen never gets busier over time.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from screensaver_app.modes import ScreensaverMode  # noqa: E402

if TYPE_CHECKING:
    from screensaver_app.settings import Settings

_CSS = b"""
.screensaver-lines-bg { background-color: #171310; }
"""
_BG_COLOR = (0x17 / 255, 0x13 / 255, 0x10 / 255)

_TICK_INTERVAL_MS = 50  # 20 fps -- smooth fades; trivial cost for at most 2 lines

_MAX_CONCURRENT_LINES = 2
_MIN_SPAWN_GAP_MS = 500
_MAX_SPAWN_GAP_MS = 1600

_FADE_IN_MS = 900
_HOLD_MS = 1100
_FADE_OUT_MS = 900
_LIFETIME_S = (_FADE_IN_MS + _HOLD_MS + _FADE_OUT_MS) / 1000.0

_MIN_WIDTH_PX = 1.5
_MAX_WIDTH_PX = 7.0
_MIN_LENGTH_FRACTION = 0.1
_MAX_LENGTH_FRACTION = 0.4
_MIN_PEAK_ALPHA = 0.45
_MAX_PEAK_ALPHA = 0.85

# Slow, calm drift -- not a fast "shooting star" sweep -- in a direction
# independent of the line's own orientation.
_MIN_SPEED_PX_S = 12.0
_MAX_SPEED_PX_S = 45.0

# A muted, warm palette (terracotta/amber/rust/sand) rather than saturated
# primaries, so each line reads as calm instead of a flash of color.
_WARM_COLORS = (
    (0.82, 0.47, 0.32),
    (0.86, 0.62, 0.32),
    (0.75, 0.42, 0.38),
    (0.90, 0.75, 0.52),
    (0.70, 0.33, 0.25),
    (0.83, 0.55, 0.40),
)


@dataclass
class _Line:
    """One line's geometry/color/velocity as of its spawn moment, plus its
    spawn time -- its current position and fade phase (in/hold/out) are
    both derived from that on every draw rather than stored, so there's
    nothing to update per-frame except pruning."""

    x0: float
    y0: float
    x1: float
    y1: float
    vx: float
    vy: float
    width: float
    color: tuple[float, float, float]
    peak_alpha: float
    spawn_time: float

    def endpoints_at(self, now: float) -> tuple[float, float, float, float]:
        """Current endpoint coordinates: the segment translates rigidly at
        ``(vx, vy)`` pixels/second from where it spawned."""
        elapsed_s = now - self.spawn_time
        dx = self.vx * elapsed_s
        dy = self.vy * elapsed_s
        return self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy

    def alpha_at(self, now: float) -> float:
        """Current opacity: ramps up over the fade-in, holds at
        ``peak_alpha``, then ramps back down over the fade-out to 0."""
        elapsed_ms = (now - self.spawn_time) * 1000.0
        if elapsed_ms < _FADE_IN_MS:
            return self.peak_alpha * (elapsed_ms / _FADE_IN_MS)
        elapsed_ms -= _FADE_IN_MS
        if elapsed_ms < _HOLD_MS:
            return self.peak_alpha
        elapsed_ms -= _HOLD_MS
        if elapsed_ms < _FADE_OUT_MS:
            return self.peak_alpha * (1.0 - elapsed_ms / _FADE_OUT_MS)
        return 0.0

    def is_expired(self, now: float) -> bool:
        return (now - self.spawn_time) >= _LIFETIME_S


class LinesMode(ScreensaverMode):
    """Random-lines mode: at most one or two line segments are visible at
    once, each drifting in its own random direction while fading in at a
    random position/length/width/color, holding briefly, fading out, and
    being replaced elsewhere after a random pause."""

    mode_id = "lines"

    def __init__(self, settings: Settings) -> None:
        """Set up per-instance timer/line state; nothing is scheduled or
        drawn until :meth:`on_start` runs."""
        super().__init__(settings)
        self._area: Gtk.DrawingArea | None = None
        self._tick_source_id: int | None = None
        self._lines: list[_Line] = []
        self._next_spawn_time = 0.0
        self._max_concurrent = 1

    def render(self, widget: Gtk.Widget) -> None:
        """Apply the dark warm background and add a ``Gtk.DrawingArea``
        that renders the currently-live lines via :meth:`_draw`."""
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        widget.add_css_class("screensaver-lines-bg")

        self._area = Gtk.DrawingArea()
        self._area.set_hexpand(True)
        self._area.set_vexpand(True)
        self._area.set_draw_func(self._draw)
        widget.append(self._area)

    def on_start(self) -> None:
        """Reset spawn/line state and start the redraw timer."""
        self._lines = []
        self._next_spawn_time = time.monotonic()
        self._max_concurrent = random.randint(1, _MAX_CONCURRENT_LINES)
        self._tick_source_id = GLib.timeout_add(_TICK_INTERVAL_MS, self._on_tick)

    def on_stop(self) -> None:
        """Cancel the redraw timer so it doesn't keep firing after the
        window showing it has been destroyed."""
        if self._tick_source_id is not None:
            GLib.source_remove(self._tick_source_id)
            self._tick_source_id = None
        self._lines = []

    def _on_tick(self) -> bool:
        """Timer callback: drop expired lines, spawn a new one if there's
        room and the random pause has elapsed, then request a redraw."""
        if self._area is None:
            return GLib.SOURCE_CONTINUE
        width = self._area.get_width()
        height = self._area.get_height()

        now = time.monotonic()
        self._lines = [line for line in self._lines if not line.is_expired(now)]

        can_spawn = width > 0 and height > 0 and now >= self._next_spawn_time
        if can_spawn and len(self._lines) < self._max_concurrent:
            self._lines.append(self._make_random_line(width, height, now))
            gap_ms = random.uniform(_MIN_SPAWN_GAP_MS, _MAX_SPAWN_GAP_MS)
            self._next_spawn_time = now + gap_ms / 1000.0
            # Re-roll the concurrency cap (1 or 2) so the pattern doesn't
            # settle into always-one or always-two.
            self._max_concurrent = random.randint(1, _MAX_CONCURRENT_LINES)

        self._area.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _make_random_line(self, width: int, height: int, now: float) -> _Line:
        """Build one line with a random position, angle, length, width, warm
        color, peak opacity, and drift velocity (its own independent random
        direction and speed), timestamped to start fading in now."""
        diagonal = math.hypot(width, height)
        length = random.uniform(_MIN_LENGTH_FRACTION, _MAX_LENGTH_FRACTION) * diagonal
        angle = random.uniform(0, math.tau)
        x0 = random.uniform(0, width)
        y0 = random.uniform(0, height)

        drift_angle = random.uniform(0, math.tau)
        speed = random.uniform(_MIN_SPEED_PX_S, _MAX_SPEED_PX_S)

        return _Line(
            x0=x0,
            y0=y0,
            x1=x0 + math.cos(angle) * length,
            y1=y0 + math.sin(angle) * length,
            vx=math.cos(drift_angle) * speed,
            vy=math.sin(drift_angle) * speed,
            width=random.uniform(_MIN_WIDTH_PX, _MAX_WIDTH_PX),
            color=random.choice(_WARM_COLORS),
            peak_alpha=random.uniform(_MIN_PEAK_ALPHA, _MAX_PEAK_ALPHA),
            spawn_time=now,
        )

    def _draw(self, _area: Gtk.DrawingArea, cr: cairo.Context, width: int, height: int) -> None:
        """``Gtk.DrawingArea`` draw function: clear to the background color,
        then stroke each currently-live line at its current fade alpha."""
        cr.set_source_rgb(*_BG_COLOR)
        cr.paint()
        if width <= 0 or height <= 0:
            return

        now = time.monotonic()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for line in self._lines:
            alpha = line.alpha_at(now)
            if alpha <= 0:
                continue
            x0, y0, x1, y1 = line.endpoints_at(now)
            r, g, b = line.color
            cr.set_source_rgba(r, g, b, alpha)
            cr.set_line_width(line.width)
            cr.move_to(x0, y0)
            cr.line_to(x1, y1)
            cr.stroke()
