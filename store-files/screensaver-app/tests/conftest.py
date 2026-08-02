"""Shared fixtures: an isolated, compiled copy of the app's GSettings schema.

Every test gets its own compiled schema directory and a fresh in-memory
settings backend (``Gio.memory_settings_backend_new()``) -- nothing here
ever touches the real dconf/user GSettings store.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def compiled_schema_source(tmp_path):
    """Compile the app's gschema into a throwaway ``tmp_path`` directory and
    return a :class:`Gio.SettingsSchemaSource` reading from it, so tests
    never depend on (or pollute) a system-wide schema install."""
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    compiler = shutil.which("glib-compile-schemas")
    if compiler is None:
        pytest.skip("glib-compile-schemas is not installed")

    subprocess.run([compiler, "--targetdir", str(tmp_path), str(DATA_DIR)], check=True)
    return Gio.SettingsSchemaSource.new_from_directory(str(tmp_path), None, False)


@pytest.fixture
def settings_factory(compiled_schema_source):
    """Return a zero-argument factory that builds a fresh
    :class:`Settings` instance backed by an isolated, in-memory GSettings
    backend -- so each call gets independent state, never the real dconf
    database."""
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    from screensaver_app.settings import Settings

    def _make() -> Settings:
        """Build one fresh, isolated Settings instance."""
        backend = Gio.memory_settings_backend_new()
        return Settings(backend=backend, schema_source=compiled_schema_source)

    return _make
