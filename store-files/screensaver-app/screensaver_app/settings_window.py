"""Preferences UI: an Adw.PreferencesWindow with General / Appearance / Slideshow / About pages.

Every control is either a direct ``Gio.Settings.bind()`` (so edits reach a
running ``main.py`` instance immediately via the GSettings change signal,
with no restart needed) or a thin ``notify::selected`` handler that writes
through :class:`screensaver_app.settings.Settings` for values that need
validation or aren't a 1:1 GObject-property match.

Note on GTK4 API drift from the original spec: ``GtkFileChooserButton`` was
removed in GTK4 (no replacement widget of the same name); the slideshow
folder picker here uses ``Gtk.FileDialog`` (the modern async replacement,
available since GTK 4.10) behind a plain button instead.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from screensaver_app import autostart  # noqa: E402
from screensaver_app.modes import ScreensaverMode, create_mode  # noqa: E402

if TYPE_CHECKING:
    from screensaver_app.idle_detector import IdleMonitor
    from screensaver_app.settings import Settings

logger = logging.getLogger(__name__)

_MODE_IDS = ("blank", "clock", "slideshow", "shader", "lines")
_MODE_LABELS = ("Blank", "Clock", "Photo Slideshow", "Shader", "Random Lines")
_TRANSITION_IDS = ("fade", "slide", "none")
_TRANSITION_LABELS = ("Fade", "Slide", "None")
_SHADER_IDS = ("gradient", "starfield")
_SHADER_LABELS = ("Flowing Gradient", "Starfield")


class PreferencesWindow(Adw.PreferencesWindow):
    """The app's whole preferences UI: four pages (General, Appearance,
    Slideshow, About) built once in :meth:`__init__`, plus a live mode
    preview that mirrors whatever's selected on the Appearance page."""

    def __init__(
        self,
        settings: Settings,
        idle_monitor: IdleMonitor | None = None,
        **kwargs,
    ) -> None:
        """Build all four preference pages, start following idle-monitor
        status changes (if an :class:`IdleMonitor` was passed in), and
        enable the live Appearance-page preview."""
        super().__init__(**kwargs)
        self._settings = settings
        self._idle_monitor = idle_monitor
        self._preview_container: Gtk.Box | None = None
        self._preview_mode: ScreensaverMode | None = None
        self._status_row: Adw.ActionRow | None = None
        self._folder_label: Gtk.Label | None = None

        self.set_title("Screensaver Preferences")
        self.set_default_size(640, 600)
        self.set_search_enabled(True)

        self.add(self._build_general_page())
        self.add(self._build_appearance_page())
        self.add(self._build_slideshow_page())
        self.add(self._build_about_page())

        if self._idle_monitor is not None:
            self._idle_monitor.connect("status-changed", self._refresh_status)
        self._refresh_status()

        self.connect("close-request", self._on_close_request)

    # -- General page ------------------------------------------------------

    def _build_general_page(self) -> Adw.PreferencesPage:
        """Build the "General" page: a live idle-detection status row, plus
        the idle-timeout, lock-on-activate, battery, inhibit, and
        launch-at-login controls."""
        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")

        status_group = Adw.PreferencesGroup(title="Status")
        self._status_row = Adw.ActionRow(title="Idle detection")
        status_group.add(self._status_row)
        page.add(status_group)

        activation_group = Adw.PreferencesGroup(title="Activation")

        timeout_row = Adw.SpinRow.new_with_range(5, 3600, 5)
        timeout_row.set_title("Idle timeout")
        timeout_row.set_subtitle("Seconds of inactivity before the screensaver starts")
        self._settings.bind("idle-timeout-seconds", timeout_row, "value")
        activation_group.add(timeout_row)

        lock_row = Adw.SwitchRow(
            title="Lock screen", subtitle="Lock the session when the screensaver activates"
        )
        self._settings.bind("lock-on-activate", lock_row, "active")
        activation_group.add(lock_row)

        battery_row = Adw.SwitchRow(
            title="Disable on battery", subtitle="Do not activate while running on battery power"
        )
        self._settings.bind("disable-on-battery", battery_row, "active")
        activation_group.add(battery_row)

        inhibit_row = Adw.SwitchRow(
            title="Respect inhibit requests",
            subtitle="Stay off while video, presentations, or games request it",
        )
        self._settings.bind("disable-when-inhibited", inhibit_row, "active")
        activation_group.add(inhibit_row)

        autostart_row = Adw.SwitchRow(
            title="Launch at login", subtitle="Start automatically when you log in"
        )
        autostart_row.set_active(self._settings.launch_at_login)
        autostart_row.connect("notify::active", self._on_launch_at_login_changed)
        activation_group.add(autostart_row)

        page.add(activation_group)
        return page

    def _on_launch_at_login_changed(self, switch_row: Adw.SwitchRow, _pspec) -> None:
        """"Launch at login" switch handler: persist the preference and
        create/remove the actual autostart ``.desktop`` file to match."""
        enabled = switch_row.get_active()
        self._settings.launch_at_login = enabled
        try:
            if enabled:
                autostart.enable()
            else:
                autostart.disable()
        except OSError:
            logger.exception("Failed to update autostart entry")

    def _refresh_status(self, *_args) -> None:
        """Rebuild the General page's status row text from the idle
        monitor's current backend/inhibit state. Called once at startup and
        again on every ``IdleMonitor`` "status-changed" signal."""
        if self._status_row is None:
            return
        if self._idle_monitor is None:
            self._status_row.set_subtitle("Live status is only available while the app is running")
            return
        backend = self._idle_monitor.backend_state
        inhibit = self._idle_monitor.inhibit_state
        parts = []
        if backend.ok:
            parts.append(f"{self._idle_monitor.session_type.value.upper()} idle detection active")
        else:
            parts.append(f"Idle detection unavailable ({backend.detail or backend.status.value})")
        if not inhibit.ok:
            parts.append(f"inhibit-watching unavailable ({inhibit.detail or inhibit.status.value})")
        elif inhibit.status is inhibit.status.OK and self._idle_monitor.is_inhibited:
            parts.append("currently inhibited by an application")
        self._status_row.set_subtitle(" · ".join(parts))

    # -- Appearance page (mode selector + live preview) -----------------------

    def _build_appearance_page(self) -> Adw.PreferencesPage:
        """Build the "Appearance" page: the live preview frame, the mode
        selector, and the clock-format/shader sub-options, then start the
        preview showing the currently selected mode."""
        page = Adw.PreferencesPage(title="Appearance", icon_name="applications-graphics-symbolic")

        preview_group = Adw.PreferencesGroup(title="Preview")
        preview_frame = Gtk.Frame()
        preview_frame.set_size_request(360, 202)
        preview_frame.set_halign(Gtk.Align.CENTER)
        self._preview_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._preview_container.set_overflow(Gtk.Overflow.HIDDEN)
        preview_frame.set_child(self._preview_container)
        preview_group.add(preview_frame)
        page.add(preview_group)

        mode_group = Adw.PreferencesGroup(title="Mode")
        mode_row = Adw.ComboRow(title="Screensaver mode")
        mode_row.set_model(Gtk.StringList.new(_MODE_LABELS))
        mode_row.set_selected(_MODE_IDS.index(self._settings.selected_mode))
        mode_row.connect("notify::selected", self._on_mode_selected)
        mode_group.add(mode_row)
        page.add(mode_group)

        clock_group = Adw.PreferencesGroup(title="Clock")
        clock_format_row = Adw.ComboRow(title="Clock format")
        clock_format_row.set_model(Gtk.StringList.new(["24-hour", "12-hour"]))
        clock_format_row.set_selected(0 if self._settings.clock_format == "24h" else 1)
        clock_format_row.connect("notify::selected", self._on_clock_format_selected)
        clock_group.add(clock_format_row)
        page.add(clock_group)

        shader_group = Adw.PreferencesGroup(title="Shader")
        shader_row = Adw.ComboRow(title="Built-in shader")
        shader_row.set_model(Gtk.StringList.new(_SHADER_LABELS))
        current_shader = self._settings.shader_selection
        shader_row.set_selected(_SHADER_IDS.index(current_shader) if current_shader in _SHADER_IDS else 0)
        shader_row.connect("notify::selected", self._on_shader_selected)
        shader_group.add(shader_row)
        page.add(shader_group)

        self._settings.preview_mode = True
        self._set_preview_mode(self._settings.selected_mode)
        return page

    def _on_mode_selected(self, combo_row: Adw.ComboRow, _pspec) -> None:
        """Mode ComboRow "notify::selected" handler: persist the new mode
        and switch the live preview to it."""
        mode_id = _MODE_IDS[combo_row.get_selected()]
        self._settings.selected_mode = mode_id
        self._set_preview_mode(mode_id)

    def _on_clock_format_selected(self, combo_row: Adw.ComboRow, _pspec) -> None:
        """Clock-format ComboRow handler: persist 24h/12h and refresh the
        preview if clock mode is the one currently selected."""
        self._settings.clock_format = "24h" if combo_row.get_selected() == 0 else "12h"
        if self._settings.selected_mode == "clock":
            self._set_preview_mode("clock")

    def _on_shader_selected(self, combo_row: Adw.ComboRow, _pspec) -> None:
        """Shader ComboRow handler: persist the chosen built-in shader and
        refresh the preview if shader mode is the one currently selected."""
        self._settings.shader_selection = _SHADER_IDS[combo_row.get_selected()]
        if self._settings.selected_mode == "shader":
            self._set_preview_mode("shader")

    def _set_preview_mode(self, mode_id: str) -> None:
        """Stop and discard whatever mode is currently rendering in the
        preview frame, then create, render, and start ``mode_id`` in its
        place. Render/start failures are logged, not raised, so a broken
        mode can't take down the settings window."""
        if self._preview_container is None:
            return
        if self._preview_mode is not None:
            try:
                self._preview_mode.on_stop()
            except Exception:
                logger.exception("Error stopping previous preview mode")
            self._preview_mode = None
        for child in list(self._preview_container):
            self._preview_container.remove(child)
        try:
            self._preview_mode = create_mode(mode_id, self._settings)
            self._preview_mode.render(self._preview_container)
            self._preview_mode.on_start()
        except Exception:  # a broken preview must not break the settings window
            logger.exception("Preview render failed for mode %r", mode_id)

    # -- Slideshow page -----------------------------------------------------

    def _build_slideshow_page(self) -> Adw.PreferencesPage:
        """Build the "Slideshow" page: the image-folder picker, the
        per-image interval, and the transition style."""
        page = Adw.PreferencesPage(title="Slideshow", icon_name="image-x-generic-symbolic")
        group = Adw.PreferencesGroup(title="Photo Slideshow")

        folder_row = Adw.ActionRow(title="Image folder")
        self._folder_label = Gtk.Label(label=self._settings.slideshow_directory)
        self._folder_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self._folder_label.set_max_width_chars(28)
        choose_button = Gtk.Button(label="Choose…")
        choose_button.set_valign(Gtk.Align.CENTER)
        choose_button.connect("clicked", self._on_choose_folder)
        folder_row.add_suffix(self._folder_label)
        folder_row.add_suffix(choose_button)
        group.add(folder_row)

        interval_row = Adw.SpinRow.new_with_range(1, 300, 1)
        interval_row.set_title("Interval")
        interval_row.set_subtitle("Seconds each photo is shown")
        self._settings.bind("slideshow-interval-seconds", interval_row, "value")
        group.add(interval_row)

        transition_row = Adw.ComboRow(title="Transition")
        transition_row.set_model(Gtk.StringList.new(_TRANSITION_LABELS))
        transition_row.set_selected(_TRANSITION_IDS.index(self._settings.slideshow_transition))
        transition_row.connect("notify::selected", self._on_transition_selected)
        group.add(transition_row)

        page.add(group)
        return page

    def _on_transition_selected(self, combo_row: Adw.ComboRow, _pspec) -> None:
        """Transition ComboRow handler: persist the chosen transition style."""
        self._settings.slideshow_transition = _TRANSITION_IDS[combo_row.get_selected()]

    def _on_choose_folder(self, _button: Gtk.Button) -> None:
        """"Choose…" button handler: open a native folder picker starting
        at the currently configured slideshow directory."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Select Slideshow Folder")
        current_dir = self._settings.slideshow_directory
        if current_dir:
            dialog.set_initial_folder(Gio.File.new_for_path(current_dir))
        dialog.select_folder(self, None, self._on_folder_dialog_finished)

    def _on_folder_dialog_finished(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        """``Gtk.FileDialog.select_folder`` completion callback: persist the
        chosen folder and update the label, or do nothing if the user
        cancelled or the dialog failed."""
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error as exc:
            logger.debug("Slideshow folder selection cancelled or failed: %s", exc)
            return
        if folder is None:
            return
        path = folder.get_path()
        if not path:
            return
        self._settings.slideshow_directory = path
        if self._folder_label is not None:
            self._folder_label.set_label(path)

    # -- About page -----------------------------------------------------------

    def _build_about_page(self) -> Adw.PreferencesPage:
        """Build the "About" page: app name/version plus a button that
        opens the full :class:`Adw.AboutWindow`."""
        page = Adw.PreferencesPage(title="About", icon_name="help-about-symbolic")
        group = Adw.PreferencesGroup()
        row = Adw.ActionRow(title="Screensaver", subtitle=_app_version())
        button = Gtk.Button(label="About Screensaver")
        button.set_valign(Gtk.Align.CENTER)
        button.connect("clicked", lambda _b: self._show_about_window())
        row.add_suffix(button)
        group.add(row)
        page.add(group)
        return page

    def _show_about_window(self) -> None:
        """"About Screensaver" button handler: build and show the standard
        libadwaita about dialog."""
        about = Adw.AboutWindow(
            transient_for=self,
            application_name="Screensaver",
            application_icon="com.alikenjo.screensaver",
            version=_app_version(),
            developer_name="alikenjo",
            license_type=Gtk.License.GPL_3_0,
            comments="A native GTK4 / libadwaita screensaver for Linux, with X11 and Wayland idle detection.",
            website="https://github.com/alikenjo/screensaver-app",
            issue_url="https://github.com/alikenjo/screensaver-app/issues",
            developers=["alikenjo"],
        )
        about.present()

    # -- teardown -------------------------------------------------------------

    def _on_close_request(self, *_args) -> bool:
        """Window "close-request" handler: stop the live preview mode and
        clear the preview-mode GSettings flag. Returns False to allow the
        close to proceed."""
        if self._preview_mode is not None:
            try:
                self._preview_mode.on_stop()
            except Exception:
                logger.exception("Error stopping preview mode on close")
            self._preview_mode = None
        self._settings.preview_mode = False
        return False


def _app_version() -> str:
    """Return the installed package's version string, for the About page."""
    from screensaver_app import __version__

    return __version__
