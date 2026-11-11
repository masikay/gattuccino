"""The preferences the extensions change while they run.

These live in the settings of the extensions (GSettings, one schema each, in
the folder of the extension), where the preferences window of an extension, the
Extensions application and this tool all see the same value, and the running
extension takes a change at once. `preferences.ini` keeps them too, so that the
file is the whole of what was chosen; whichever was changed last is the one
the next `configure` starts from.
"""

import ast
import copy
import os
from dataclasses import dataclass

from . import preferences as prefs
from .desktop import Desktop

BLUR_UUID = "blur@gattuccino"
FLOATING_PANEL_UUID = "floating-panel@gattuccino"
ACCENT_UUID = "catppuccin-accent@gattuccino"

INT, BOOL, TEXT = "int", "bool", "text"


@dataclass(frozen=True)
class Key:
    uuid: str        # the extension whose setting it is
    schema: str
    key: str
    kind: str        # INT, BOOL or TEXT


LIVE = {
    "blur_radius": Key(BLUR_UUID, "org.gnome.shell.extensions.gattuccino-blur", "radius", INT),
    "blur_background": Key(BLUR_UUID, "org.gnome.shell.extensions.gattuccino-blur", "background", BOOL),
    "blur_background_radius": Key(BLUR_UUID, "org.gnome.shell.extensions.gattuccino-blur",
                                  "background-radius", INT),
    "panel_gap": Key(FLOATING_PANEL_UUID, "org.gnome.shell.extensions.gattuccino-floating-panel", "gap", INT),
    "panel_radius": Key(FLOATING_PANEL_UUID, "org.gnome.shell.extensions.gattuccino-floating-panel",
                        "radius", TEXT),
    "dock_radius": Key(ACCENT_UUID, "org.gnome.shell.extensions.gattuccino-accent", "dock-radius", TEXT),
    "show_apps_icon": Key(ACCENT_UUID, "org.gnome.shell.extensions.gattuccino-accent", "show-apps-icon", TEXT),
}
assert set(LIVE) == prefs.LIVE_NAMES


def schema_args(desktop: Desktop, key: Key):
    """The gsettings arguments that reach the setting, or None while the extension is not installed
    (its schema is in its own folder, and is compiled when it is installed)."""
    schemas = f"{desktop.extensions_dir}/{key.uuid}/schemas"
    if os.path.exists(f"{schemas}/gschemas.compiled"):
        return ("--schemadir", schemas)
    return None


def available(desktop: Desktop) -> set:
    """Which of the live preferences have a setting to be read and written."""
    return {name for name, key in LIVE.items() if schema_args(desktop, key) is not None}


def _read(desktop: Desktop, key: Key):
    args = schema_args(desktop, key)
    if args is None:
        return None
    result = desktop.run("gsettings", *args, "get", key.schema, key.key)
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    try:
        if key.kind == BOOL:
            return text == "true"
        if key.kind == INT:
            return int(text.split()[-1])   # an int with a range prints as 'uint32 3' elsewhere
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None


def _text_of_setting(name: str, value) -> str:
    """A setting in the form a preference is typed in."""
    key = LIVE[name]
    if key.kind == BOOL:
        return "yes" if value else "no"
    if name == "show_apps_icon":
        return value or prefs.ICON_DEFAULT
    return str(value)


def _setting_of_preference(name: str, preferences: prefs.Preferences):
    """A preference in the form the setting is written in: a Python value."""
    key = LIVE[name]
    value = getattr(preferences, name)
    if key.kind == BOOL:
        return bool(value)
    if key.kind == INT:
        return int(value)
    return preferences.text(name) if name != "show_apps_icon" else (value or "")


def pull(desktop: Desktop, preferences: prefs.Preferences, only=None) -> list:
    """Take the values the settings have now, so that a change made in the
    preferences of an extension is not undone by the file. Returns the names changed."""
    changed = []
    for name, key in LIVE.items():
        if only is not None and name not in only:
            continue
        value = _read(desktop, key)
        if value is None:
            continue
        try:
            trial = copy.copy(preferences)
            trial.set(name, _text_of_setting(name, value))
        except prefs.PreferenceError:
            continue   # a file that has gone, say: the one in the preferences stays
        if getattr(trial, name) != getattr(preferences, name):
            setattr(preferences, name, getattr(trial, name))
            changed.append(name)
    return changed


def push(desktop: Desktop, preferences: prefs.Preferences, only=None) -> list:
    """Write the preferences into the settings of the extensions that are installed,
    where the running extensions take them at once. Returns the names written."""
    written = []
    for name, key in LIVE.items():
        if only is not None and name not in only:
            continue
        args = schema_args(desktop, key)
        if args is None:
            continue
        value = _setting_of_preference(name, preferences)
        if _read(desktop, key) == value:
            continue
        text = ("true" if value else "false") if key.kind == BOOL else (str(value) if key.kind == INT else repr(value))
        if desktop.run("gsettings", *args, "set", key.schema, key.key, text).returncode == 0:
            written.append(name)
    return written


def reset(desktop: Desktop):
    """Give the settings back their defaults, before the extensions that own them go."""
    for schema in sorted({key.schema for key in LIVE.values()}):
        key = next(key for key in LIVE.values() if key.schema == schema)
        args = schema_args(desktop, key)
        if args is not None:
            desktop.run("gsettings", *args, "reset-recursively", schema)
