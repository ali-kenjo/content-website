"""GLSL fragment-shader mode, rendered via GtkGLArea with shadertoy-style uniforms.

Ships two built-in shaders (a flowing gradient, a starfield) as package data
under ``screensaver_app.shaders`` so lookup works the same whether running
from a source checkout or an installed wheel/flatpak. ``shader-selection``
can also be an absolute path to a user-supplied ``.frag`` file -- both
built-ins and custom files only need to expose ``iTime`` (float, seconds)
and ``iResolution`` (vec2, pixels) uniforms and write ``fragColor``.
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import time
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

try:
    from OpenGL import GL
except ImportError:  # pragma: no cover - surfaced as a render error, not a crash
    GL = None

from screensaver_app.modes import ScreensaverMode  # noqa: E402

if TYPE_CHECKING:
    from screensaver_app.settings import Settings

logger = logging.getLogger(__name__)

_SHADERS_PACKAGE = "screensaver_app.shaders"
BUILTIN_SHADERS = ("gradient", "starfield")
_DEFAULT_SHADER = "gradient"

_VERTEX_SHADER_SRC = """
#version 330 core
layout(location = 0) in vec2 position;
void main() {
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

# A full-viewport triangle strip (2 triangles).
_QUAD_VERTICES = (-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0)
_FRAME_INTERVAL_MS = 16  # ~60 fps redraw request; actual GL rendering is vsync-gated by GtkGLArea


def _read_builtin_shader(name: str) -> str:
    """Read a built-in ``.frag`` file's source from the package data."""
    return resources.files(_SHADERS_PACKAGE).joinpath(f"{name}.frag").read_text()


class ShaderMode(ScreensaverMode):
    """GLSL fragment-shader mode: renders a full-viewport quad through a
    user-selected (or custom) fragment shader via ``Gtk.GLArea``."""

    mode_id = "shader"

    def __init__(self, settings: Settings) -> None:
        """Set up per-instance GL/timer state; no GL context exists until
        the ``Gtk.GLArea`` created in :meth:`render` is realized."""
        super().__init__(settings)
        self._gl_area: Gtk.GLArea | None = None
        self._program: int | None = None
        self._vao: int | None = None
        self._vbo: int | None = None
        self._start_time = 0.0
        self._tick_source_id: int | None = None
        self.last_error: str | None = None

    def render(self, widget: Gtk.Widget) -> None:
        """Create the ``Gtk.GLArea`` and wire up its realize/unrealize/
        render signals to the GL lifecycle methods below."""
        self._gl_area = Gtk.GLArea()
        self._gl_area.set_hexpand(True)
        self._gl_area.set_vexpand(True)
        self._gl_area.set_auto_render(True)
        with contextlib.suppress(Exception):  # not all GL drivers accept an explicit request
            self._gl_area.set_required_version(3, 3)
        self._gl_area.connect("realize", self._on_realize)
        self._gl_area.connect("unrealize", self._on_unrealize)
        self._gl_area.connect("render", self._on_render)
        widget.append(self._gl_area)

    def on_start(self) -> None:
        """Record the animation start time and begin requesting redraws at
        ``_FRAME_INTERVAL_MS`` (actual GL rendering stays vsync-gated by
        ``Gtk.GLArea`` itself)."""
        self._start_time = time.monotonic()
        self._tick_source_id = GLib.timeout_add(_FRAME_INTERVAL_MS, self._on_tick)

    def on_stop(self) -> None:
        """Cancel the redraw-request timer so it doesn't keep firing after
        the window showing it has been destroyed."""
        if self._tick_source_id is not None:
            GLib.source_remove(self._tick_source_id)
            self._tick_source_id = None

    def _on_tick(self) -> bool:
        """Redraw-request timer callback: ask the GL area to redraw on its
        next vsync-gated frame."""
        if self._gl_area is not None:
            self._gl_area.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _resolve_fragment_source(self) -> str:
        """Resolve the configured shader selection to GLSL source: a
        built-in name reads package data, anything else is treated as a
        path to a custom ``.frag`` file (falling back to the default
        built-in shader if that file can't be read)."""
        selection = self.settings.shader_selection
        if selection in BUILTIN_SHADERS:
            return _read_builtin_shader(selection)
        try:
            return Path(selection).read_text()
        except OSError as exc:
            logger.warning(
                "Failed to read custom shader %r, falling back to %r: %s",
                selection,
                _DEFAULT_SHADER,
                exc,
            )
            return _read_builtin_shader(_DEFAULT_SHADER)

    # -- GL lifecycle ---------------------------------------------------------

    def _on_realize(self, area: Gtk.GLArea) -> None:
        """``Gtk.GLArea`` "realize" handler: make the GL context current
        and compile/link the shader program plus the full-viewport quad.
        Any failure is recorded in ``last_error`` (surfaced by
        :meth:`_on_render` as a cleared black frame) rather than raised."""
        area.make_current()
        if area.get_error() is not None:
            self.last_error = str(area.get_error())
            logger.error("GL context error on realize: %s", self.last_error)
            return
        if GL is None:
            self.last_error = "PyOpenGL is not installed"
            logger.error(self.last_error)
            return
        try:
            fragment_src = self._resolve_fragment_source()
            self._program = self._compile_program(_VERTEX_SHADER_SRC, fragment_src)
            self._vao, self._vbo = self._setup_quad()
        except Exception as exc:  # noqa: BLE001 - render() below falls back to a clear frame
            self.last_error = str(exc)
            logger.error("Shader setup failed: %s", exc)

    def _on_unrealize(self, area: Gtk.GLArea) -> None:
        """``Gtk.GLArea`` "unrealize" handler: free the GL objects created
        in :meth:`_on_realize` while the context is still current."""
        if GL is None:
            return
        area.make_current()
        if self._vbo is not None:
            GL.glDeleteBuffers(1, [self._vbo])
            self._vbo = None
        if self._vao is not None:
            GL.glDeleteVertexArrays(1, [self._vao])
            self._vao = None
        if self._program is not None:
            GL.glDeleteProgram(self._program)
            self._program = None

    def _on_render(self, area: Gtk.GLArea, _gl_context) -> bool:
        """``Gtk.GLArea`` "render" handler: clear the viewport, then (if
        the shader compiled successfully) bind the program, push the
        ``iTime``/``iResolution`` uniforms, and draw the full-viewport quad."""
        if GL is None:
            return True
        width = max(1, area.get_width() * area.get_scale_factor())
        height = max(1, area.get_height() * area.get_scale_factor())
        GL.glViewport(0, 0, width, height)
        GL.glClearColor(0.0, 0.0, 0.0, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        if self._program is None or self._vao is None:
            return True  # cleared to black; last_error carries the reason

        GL.glUseProgram(self._program)
        elapsed = time.monotonic() - self._start_time
        time_loc = GL.glGetUniformLocation(self._program, "iTime")
        res_loc = GL.glGetUniformLocation(self._program, "iResolution")
        if time_loc != -1:
            GL.glUniform1f(time_loc, elapsed)
        if res_loc != -1:
            GL.glUniform2f(res_loc, float(width), float(height))

        GL.glBindVertexArray(self._vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
        GL.glBindVertexArray(0)
        return True

    # -- GL setup helpers -------------------------------------------------------

    def _compile_shader(self, shader_type: int, source: str) -> int:
        """Compile a single GLSL shader stage; raises RuntimeError with the
        driver's compile log on failure."""
        shader = GL.glCreateShader(shader_type)
        GL.glShaderSource(shader, source)
        GL.glCompileShader(shader)
        if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
            log = GL.glGetShaderInfoLog(shader)
            GL.glDeleteShader(shader)
            raise RuntimeError(f"shader compile error: {log.decode() if isinstance(log, bytes) else log}")
        return shader

    def _compile_program(self, vertex_src: str, fragment_src: str) -> int:
        """Compile and link a vertex+fragment shader pair into a GL
        program; raises RuntimeError with the driver's link log on failure."""
        vertex_shader = self._compile_shader(GL.GL_VERTEX_SHADER, vertex_src)
        fragment_shader = self._compile_shader(GL.GL_FRAGMENT_SHADER, fragment_src)
        program = GL.glCreateProgram()
        GL.glAttachShader(program, vertex_shader)
        GL.glAttachShader(program, fragment_shader)
        GL.glLinkProgram(program)
        GL.glDeleteShader(vertex_shader)
        GL.glDeleteShader(fragment_shader)
        if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
            log = GL.glGetProgramInfoLog(program)
            GL.glDeleteProgram(program)
            raise RuntimeError(f"shader link error: {log.decode() if isinstance(log, bytes) else log}")
        return program

    def _setup_quad(self) -> tuple[int, int]:
        """Upload ``_QUAD_VERTICES`` into a VAO/VBO pair covering the full
        viewport (two triangles), for the fragment shader to paint over."""
        vao = GL.glGenVertexArrays(1)
        vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
        vertex_array = (ctypes.c_float * len(_QUAD_VERTICES))(*_QUAD_VERTICES)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, ctypes.sizeof(vertex_array), vertex_array, GL.GL_STATIC_DRAW)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glEnableVertexAttribArray(0)
        GL.glBindVertexArray(0)
        return vao, vbo
