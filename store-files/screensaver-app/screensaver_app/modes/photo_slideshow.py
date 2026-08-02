"""Cycles images from the configured directory with a crossfade/slide/none transition."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from screensaver_app.modes import ScreensaverMode

if TYPE_CHECKING:
    from screensaver_app.settings import Settings

logger = logging.getLogger(__name__)

_CSS = b"""
.screensaver-slideshow-bg { background-color: #000000; }
.screensaver-slideshow-placeholder { color: #808080; font-size: 18pt; }
"""

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".gif"})
_TRANSITION_MAP = {
    "fade": Gtk.StackTransitionType.CROSSFADE,
    "slide": Gtk.StackTransitionType.SLIDE_LEFT,
    "none": Gtk.StackTransitionType.NONE,
}
_TRANSITION_DURATION_MS = 900


class PhotoSlideshowMode(ScreensaverMode):
    """Cycles through images from the configured directory in a
    ``Gtk.Stack``, using the stack's built-in transition to crossfade/slide
    between them."""

    mode_id = "slideshow"

    def __init__(self, settings: Settings) -> None:
        """Set up per-instance state; images aren't discovered or shown
        until :meth:`render` runs."""
        super().__init__(settings)
        self._stack: Gtk.Stack | None = None
        self._timer_source_id: int | None = None
        self._image_paths: list[Path] = []
        self._index = -1
        self._next_name_counter = 0

    def render(self, widget: Gtk.Widget) -> None:
        """Set up the black background and transition-configured
        ``Gtk.Stack``, discover images in the configured directory, and
        show either the first image or a "no images found" placeholder."""
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        widget.add_css_class("screensaver-slideshow-bg")

        self._stack = Gtk.Stack()
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)
        transition = _TRANSITION_MAP.get(
            self.settings.slideshow_transition, Gtk.StackTransitionType.CROSSFADE
        )
        self._stack.set_transition_type(transition)
        self._stack.set_transition_duration(_TRANSITION_DURATION_MS)
        widget.append(self._stack)

        self._image_paths = self._discover_images()
        if not self._image_paths:
            placeholder = Gtk.Label(label="No images found in the slideshow folder")
            placeholder.add_css_class("screensaver-slideshow-placeholder")
            self._stack.add_named(placeholder, "placeholder")
            self._stack.set_visible_child_name("placeholder")
            return

        self._show_next_image()

    def on_start(self) -> None:
        """Start the per-image advance timer at the configured interval
        (minimum 1 second)."""
        interval = max(1, self.settings.slideshow_interval_seconds)
        self._timer_source_id = GLib.timeout_add_seconds(interval, self._on_timer)

    def on_stop(self) -> None:
        """Cancel the advance timer so it doesn't keep firing after the
        window showing it has been destroyed."""
        if self._timer_source_id is not None:
            GLib.source_remove(self._timer_source_id)
            self._timer_source_id = None

    def _discover_images(self) -> list[Path]:
        """List and sort every file in the configured slideshow directory
        whose extension looks like an image. Returns an empty list (with a
        warning logged) if the directory doesn't exist."""
        directory = Path(self.settings.slideshow_directory)
        if not directory.is_dir():
            logger.warning("Slideshow directory does not exist: %s", directory)
            return []
        return sorted(
            p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
        )

    def _on_timer(self) -> bool:
        """Per-image advance timer callback: show the next image."""
        self._show_next_image()
        return GLib.SOURCE_CONTINUE

    def _show_next_image(self) -> None:
        """Advance to and load the next loadable image (skipping any that
        fail to decode), add it to the stack under a fresh name so the
        transition animates in, and schedule the previous images' removal
        once that transition finishes."""
        if not self._image_paths or self._stack is None:
            return

        picture = None
        for _ in range(len(self._image_paths)):
            self._index = (self._index + 1) % len(self._image_paths)
            picture = self._load_picture(self._image_paths[self._index])
            if picture is not None:
                break
        if picture is None:
            logger.warning("All images in slideshow directory failed to load")
            return

        stale_children = list(self._iter_children())
        self._next_name_counter += 1
        name = f"img-{self._next_name_counter}"
        self._stack.add_named(picture, name)
        self._stack.set_visible_child_name(name)

        duration = self._stack.get_transition_duration()
        GLib.timeout_add(duration + 50, lambda: self._prune(stale_children))

    def _iter_children(self):
        """Yield the stack's child widgets in order (there's no built-in
        iterator on ``Gtk.Stack``, so this walks the sibling chain)."""
        if self._stack is None:
            return
        child = self._stack.get_first_child()
        while child is not None:
            yield child
            child = child.get_next_sibling()

    def _prune(self, children: list[Gtk.Widget]) -> bool:
        """Deferred cleanup callback: remove the given (now stale, already
        transitioned-away-from) children from the stack, once the
        crossfade/slide transition that replaced them has finished."""
        if self._stack is not None:
            for child in children:
                if child.get_parent() is self._stack:
                    self._stack.remove(child)
        return GLib.SOURCE_REMOVE

    def _load_picture(self, path: Path) -> Gtk.Picture | None:
        """Load ``path`` as a ``Gtk.Picture`` (applying EXIF orientation),
        or return None (with a warning logged) if it can't be decoded."""
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
            pixbuf = pixbuf.apply_embedded_orientation()
        except GLib.Error as exc:
            logger.warning("Skipping unreadable/corrupt image %s: %s", path, exc)
            return None
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_hexpand(True)
        picture.set_vexpand(True)
        return picture
