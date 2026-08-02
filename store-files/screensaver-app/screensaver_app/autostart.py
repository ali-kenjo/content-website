"""Generates/removes the XDG autostart .desktop entry for "Launch at login".

The entry's ``Exec=`` line always resolves the command at write-time
(preferring the installed ``screensaver-app`` console script, falling back
to invoking the current interpreter against the package) rather than baking
in a path fixed at build time -- so a dev checkout and an installed package
both produce a working entry.
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from screensaver_app import APPLICATION_ID  # noqa: E402

logger = logging.getLogger(__name__)

_DESKTOP_FILE_NAME = f"{APPLICATION_ID}.desktop"


def _autostart_dir() -> Path:
    """The XDG autostart directory (``~/.config/autostart`` by default)."""
    return Path(GLib.get_user_config_dir()) / "autostart"


def _autostart_path() -> Path:
    """Full path to this app's autostart ``.desktop`` file."""
    return _autostart_dir() / _DESKTOP_FILE_NAME


def _resolve_exec_command() -> str:
    """Command to put in the entry's ``Exec=`` line: the installed
    ``screensaver-app`` console script if one is on PATH, else the current
    interpreter invoking the package directly (dev checkout case)."""
    installed = shutil.which("screensaver-app")
    if installed:
        return installed
    return f"{sys.executable} -m screensaver_app.main"


def is_enabled() -> bool:
    """Whether an autostart entry exists and isn't explicitly disabled."""
    path = _autostart_path()
    if not path.exists():
        return False
    try:
        content = path.read_text()
    except OSError:
        return False
    for line in content.splitlines():
        if line.strip().startswith("X-GNOME-Autostart-enabled"):
            return line.split("=", 1)[1].strip().lower() == "true"
    return True


def enable() -> Path:
    """Write (or overwrite) the autostart entry. Returns the written path."""
    autostart_dir = _autostart_dir()
    autostart_dir.mkdir(parents=True, exist_ok=True)
    path = _autostart_path()
    exec_command = _resolve_exec_command()
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Screensaver\n"
        "Comment=Native GTK4 screensaver\n"
        f"Exec={exec_command}\n"
        "Terminal=false\n"
        "NoDisplay=true\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    path.write_text(content)
    logger.info("Autostart entry written to %s (Exec=%s)", path, exec_command)
    return path


def disable() -> None:
    """Remove the autostart entry entirely -- a clean uninstall, not a flag flip."""
    path = _autostart_path()
    try:
        path.unlink()
        logger.info("Autostart entry removed: %s", path)
    except FileNotFoundError:
        pass
