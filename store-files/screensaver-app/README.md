# Screensaver

A native GTK4 / libadwaita screensaver for Linux, targeting Pop!_OS 24.04
(GNOME and COSMIC), with idle detection on both Wayland (`ext-idle-notify-v1`)
and X11 (the MIT-SCREEN-SAVER extension).

## Open source, free to use however you like

This app was built on Pop!_OS Linux, largely through "vibe coding" (prompting
an AI coding assistant rather than hand-typing every line). It's offered as-is,
so please be a courteous user: try it on a spare account or VM first if you're
cautious, and keep normal backups/updates hygiene on your own machine like you
would for any new software.

It's licensed under the **GNU GPL-3.0-or-later** (see [`LICENSE`](LICENSE)),
which means you are free to:

- **Use** it for anything, personal or commercial.
- **Read, edit, and modify** the source however you like.
- **Integrate** it into your own projects or distributions.
- **Redistribute** it, modified or not, to anyone.
- **Download** it at no cost, no account, no strings attached.

The only real condition is the standard copyleft one: if you redistribute a
modified version, keep it open source under the same license too. See
[Installing it](#installing-it) and [Modifying it locally](#modifying-it-locally)
below to get started.

## Features

- Idle detection: event-driven on Wayland, 1&nbsp;Hz-polled on X11, with a
  visible "unsupported" status (never a crash) if the compositor/session
  doesn't support either.
- Hosts `org.freedesktop.ScreenSaver` itself so video players, presentations,
  and games can inhibit activation the same way they do on other desktops.
- Five modes: blank, clock (with periodic position drift to avoid burn-in),
  photo slideshow (EXIF-aware, crossfade/slide/none transitions), GLSL
  shaders (two built in: a flowing gradient and a starfield) via `GtkGLArea`,
  and random lines (one or two calm, warm-colored line segments of random
  position, length, and width, fading in and out at random spots on a dark
  background).
- Runs on every connected monitor simultaneously; any input on any monitor
  dismisses all of them.
- Optional session lock on activation, via `org.gnome.ScreenSaver` or
  `org.freedesktop.login1`, whichever is available.
- Live preferences: every setting is a GSettings key, so changes in the
  preferences window apply to a running instance immediately -- no restart.
- Tray icon via a hand-rolled StatusNotifierItem + DBusMenu D-Bus service
  (see "Why not AppIndicator3?" below), plus `screensaver-app --preferences`
  / `--preview` for when no tray host is available.

## Project layout

```
screensaver_app/
├── main.py              # Adw.Application, tray icon, signal handling
├── idle_detector.py      # X11/Wayland idle detection + inhibit watching
├── settings.py            # typed GSettings wrapper
├── settings_window.py    # Adw.PreferencesWindow
├── display_window.py      # fullscreen per-monitor screensaver windows
├── modes/                  # blank / clock / photo_slideshow / shader / lines
├── shaders/                 # built-in .frag files (package data)
└── autostart.py            # ~/.config/autostart/*.desktop management
data/                        # gschema, .desktop, AppStream metainfo, icon
flatpak/                     # flatpak-builder manifest
tests/                       # pytest suite
```

## Requirements

System packages (Debian/Ubuntu/Pop!_OS names):

```
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
    libglib2.0-dev libcairo2-dev python3-dev
```

Python dependencies are listed in `pyproject.toml` (PyGObject, python-xlib,
pywayland, dbus-next, PyOpenGL) and installed automatically by pip/flatpak.

## Installing it

Download and extract the source (or `git clone` it if you got it from a
repository), then, from inside the `screensaver-app` folder:

```bash
# System packages (see Requirements above) need to be installed first.
pip install .
```

This installs the app as a regular command, `screensaver-app`, plus its
GSettings schema. Run it once to register everything, then launch it either
from your app grid (it installs a `.desktop` entry) or from a terminal:

```bash
screensaver-app
```

Turn on "Launch at login" in the preferences window (see below) so it starts
automatically every session, the same as any other screensaver.

Prefer Flatpak, or want a fully sandboxed install instead? See
[Packaging](#packaging) below.

## How to use it

- **Preferences window**: run `screensaver-app --preferences`, or click the
  tray icon (if your desktop shows one) and choose "Preferences". From
  there you can pick a mode (Blank, Clock, Photo Slideshow, Shader, or
  Random Lines), set the idle timeout, turn on session locking, and more --
  every change applies live, with a preview right in the window.
- **Preview it right now**: `screensaver-app --preview`, or the tray icon's
  "Preview now" action, triggers the screensaver immediately without
  waiting for the idle timeout -- handy for checking a mode/setting change.
- **Dismissing it**: any keyboard or mouse input on any monitor closes the
  screensaver on every monitor at once.
- **Autostart**: toggle "Launch at login" in the preferences window's
  General page to have it start automatically every session.

## Modifying it locally

Same starting point as installing (download/clone the source), but install
it in "editable" mode with the dev extras instead, so your edits under
`screensaver_app/` take effect the next time you run it -- no reinstall step:

```bash
cd screensaver-app

# Compile the GSettings schema in place so the app can run straight from
# the source tree without a system-wide install (settings.py auto-detects
# data/gschemas.compiled and uses it as a fallback schema source):
glib-compile-schemas data/

pip install -e '.[dev]'

screensaver-app
```

Because GSettings is dconf-backed, preferences persist under
`/com/alikenjo/screensaver/` in your normal dconf database during
development too -- `dconf reset -f /com/alikenjo/screensaver/` clears them.

Want to add a new screensaver mode of your own? Every mode is a small,
self-contained class implementing `ScreensaverMode` in
`screensaver_app/modes/` (see `blank.py` for the simplest example, or
`lines.py` for one with animation/timers) -- register it in
`screensaver_app/modes/__init__.py`'s `create_mode()` and it'll show up in
the preferences window's mode dropdown once you add it to
`settings_window.py`'s `_MODE_IDS`/`_MODE_LABELS` too.

## Testing

```bash
ruff check .
pytest
```

`tests/` covers the idle-timeout crossing/hysteresis logic (X11 and Wayland
handlers, both mocked at the point where the real backends would call in)
and GSettings round-trip persistence (against an isolated, compiled copy of
the schema + an in-memory backend -- never your real dconf database).

## Packaging

- **Wheel/sdist**: `python -m build` (hatchling backend, console-script
  entry point `screensaver-app`).
- **Flatpak**: see `flatpak/com.alikenjo.screensaver.yaml`. The Python
  dependency module is a placeholder -- regenerate it from
  `flatpak/requirements.txt` with `flatpak-pip-generator` before a real
  build, since Flathub builds have no network access (instructions are in
  the manifest's comments). Then:

  ```bash
  flatpak-builder --user --install build-dir flatpak/com.alikenjo.screensaver.yaml
  ```

## Why not AppIndicator3?

The obvious way to get a tray icon on GNOME/COSMIC is
`AppIndicator3`/`AyatanaAppIndicator3`, but that library's C API takes a
GTK3 `Gtk.Menu` -- and GTK3 cannot be loaded in the same process as GTK4
(this app), since both toolkits register conflicting global GType state.
Rather than pull in a second toolkit, `main.py` implements a small
`StatusNotifierItem` + `com.canonical.dbusmenu` service directly over D-Bus.
If no StatusNotifierWatcher host is running (a stock GNOME Shell session
without the "AppIndicator and KStatusNotifierItem Support" extension), the
icon just won't appear -- the app keeps running regardless and stays
reachable via the CLI flags above, which GApplication forwards to the
already-running instance.

## Manual test checklist

These require a real desktop session and can't be meaningfully automated:

- [ ] **Multi-monitor**: with 2+ monitors connected, trigger the screensaver
      (`screensaver-app --preview` or wait out the idle timeout) and confirm
      a fullscreen window appears on *every* monitor, all showing the same
      mode, and that moving the mouse on any single monitor dismisses all
      of them at once.
- [ ] **Inhibit on fullscreen video**: play a video fullscreen in a player
      that calls `org.freedesktop.ScreenSaver.Inhibit` (e.g. `mpv`,
      Firefox/Chromium playing video), sit idle past the timeout, and
      confirm the screensaver does *not* activate. Close the player and
      confirm it activates normally afterward. Check Preferences -> General
      -> Status reflects "currently inhibited by an application" while the
      inhibit is held.
- [ ] **Battery toggle**: with "Disable on battery" on, unplug AC power,
      idle past the timeout, and confirm no activation; plug back in and
      confirm it activates normally. (Requires UPower; on a desktop with no
      battery this is untestable and is treated as "not on battery".)
- [ ] **Lock-on-resume**: with "Lock screen" enabled, trigger the
      screensaver and confirm the session lock screen appears alongside/
      before the screensaver content, and that dismissing the screensaver
      requires re-authentication.
- [ ] **Autostart entry correctness**: toggle "Launch at login" on, confirm
      `~/.config/autostart/com.alikenjo.screensaver.desktop` is created with
      `Exec=` pointing at the installed `screensaver-app` binary (not a dev
      checkout path), `Terminal=false`, and
      `X-GNOME-Autostart-enabled=true`. Toggle it off and confirm the file
      is removed. Log out/in (or `gnome-session-quit --logout`) to confirm
      it actually launches at login.
- [ ] **Wayland without ext-idle-notify-v1**: on a compositor that doesn't
      support the protocol, confirm the app doesn't crash or hang -- General
      -> Status should show idle detection as unavailable, with the tray
      "Preview now" action still working as a manual trigger.
- [ ] **Tray icon**: confirm the icon appears on a host that registers
      `org.kde.StatusNotifierWatcher` (COSMIC panel, or GNOME Shell with the
      AppIndicator extension) and that all four menu actions work. On a
      host without a watcher, confirm the app still starts cleanly and
      `screensaver-app --preferences` opens the settings window.

## License

GPL-3.0-or-later -- see [`LICENSE`](LICENSE) for the full text.
