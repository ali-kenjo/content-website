"""Built-in GLSL fragment shaders, shipped as package data.

Not Python modules -- this package exists so the .frag files next to it are
resolvable via importlib.resources regardless of install layout (wheel,
zipapp, editable install, ...), instead of a path computed relative to
``__file__`` that breaks once the app is packaged.
"""
