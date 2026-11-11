"""The preferences: what they are, how they are checked, where they are kept."""

import configparser
import os
from dataclasses import dataclass, fields
from typing import Optional, Union

from . import palette

HELP_ACCENT_SELECTION = (
    "Use the accent color for selected sidebar rows and highlighted menu items in "
    "applications, where GNOME uses a shade of the text color"
)

FOLLOW = "follow"  # accent: whatever is picked in Settings > Appearance
AUTO = "auto"      # shell_version: the installed GNOME Shell
# blur was once offered in two kinds, plain and frosted; frosted is gone, and
# both of the words an earlier version wrote in the file still mean yes
LEGACY_BLUR_KINDS = ("plain", "frosted")


class PreferenceError(Exception):
    pass


def _opacity(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise PreferenceError("expected a number between 0 (invisible) and 1 (opaque)") from None
    if not 0 <= value <= 1:
        raise PreferenceError("expected a number between 0 (invisible) and 1 (opaque)")
    return value


def _blur(text: str) -> bool:
    if text.strip().lower() in LEGACY_BLUR_KINDS:
        return True
    return _boolean(text)


def _boolean(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in ("yes", "y", "true", "on", "1"):
        return True
    if lowered in ("no", "n", "false", "off", "0"):
        return False
    raise PreferenceError("expected yes or no")


def _choice(*choices):
    def parse(text: str) -> str:
        value = text.strip().lower()
        if value not in choices:
            raise PreferenceError(f"expected one of: {', '.join(choices)}")
        return value
    return parse


def _dark_flavor(text: str) -> str:
    value = text.strip().lower()
    if value == palette.LIGHT_FLAVOR:
        raise PreferenceError(f"{value} is always installed for the light style: "
                              f"choose the flavor of the dark style, one of: {', '.join(palette.DARK_FLAVORS)}")
    return _choice(*palette.DARK_FLAVORS)(value)


def _pixels(maximum: int):
    def parse(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise PreferenceError(f"expected a whole number between 0 and {maximum}") from None
        if not 0 <= value <= maximum:
            raise PreferenceError(f"expected a whole number between 0 and {maximum}")
        return value
    return parse


def _radius(text: str):
    return None if text.strip().lower() == "round" else _pixels(100)(text)


DOCK = "dock"    # dock_radius: whatever Dash to Dock draws
ROUND = "round"  # dock_radius: as round as the floating top bar


def _dock_radius(text: str):
    value = text.strip().lower()
    if value == DOCK:
        return None
    return ROUND if value == ROUND else _pixels(100)(text)


ICON_DEFAULT = "default"   # show_apps_icon: the icon GNOME draws
ICON_SUFFIXES = (".svg", ".png")
ICON_FLAVOR = "{flavor}"   # show_apps_icon: stands for the flavor in use


def icon_files(path: str):
    """The files a show_apps_icon can be: one, or one for each flavor if it has {flavor} in it."""
    if ICON_FLAVOR not in path:
        return [path]
    return [path.replace(ICON_FLAVOR, flavor) for flavor in (palette.LIGHT_FLAVOR, *palette.DARK_FLAVORS)]


def _icon_file(text: str):
    value = text.strip()
    if value.lower() in ("", ICON_DEFAULT):
        return None
    path = os.path.abspath(os.path.expanduser(value))
    if not path.lower().endswith(ICON_SUFFIXES):
        raise PreferenceError("expected an .svg or .png file, or 'default'")
    files = icon_files(path)
    if not any(os.path.isfile(file) for file in files):
        raise PreferenceError(f"{files[0] if len(files) == 1 else path} was not found")
    return path


def _docked_opacity(text: str):
    return None if text.strip().lower() == "same" else _opacity(text)


def _shell_version(text: str) -> str:
    from . import sources
    value = text.strip().lower()
    if value != AUTO:
        try:
            sources.check_version(value)
        except sources.SourcesError as e:
            raise PreferenceError(str(e)) from None
    return value


@dataclass(frozen=True)
class Spec:
    parse: callable
    values: str   # what can be entered, for help texts
    help: str
    none_as: Optional[str] = None  # how a None value is written


# Declaration order is the order of the questions asked by `configure`.
SPECS = {
    "flavor": Spec(_dark_flavor, ", ".join(palette.DARK_FLAVORS),
                   "Catppuccin flavor of the dark style (latte is used for the light style): "
                   "mocha is the darkest"),
    "accent": Spec(_choice(FOLLOW, *palette.ACCENTS), f"{FOLLOW}, {', '.join(palette.ACCENTS)}",
                   f"Accent color; '{FOLLOW}' uses the one picked in Settings > Appearance"),
    "shell_theme": Spec(_boolean, "yes, no", "Install the GNOME Shell theme in ~/.themes"),
    "gtk_theme": Spec(_boolean, "yes, no",
                      "Install the application colors in ~/.config/gtk-4.0 and ~/.config/gtk-3.0"),
    "flatpak": Spec(_boolean, "yes, no", "Let Flatpak applications read the application colors"),
    "accent_selection": Spec(_boolean, "yes, no", HELP_ACCENT_SELECTION),
    "panel_opacity": Spec(_opacity, "0 to 1", "Opacity of the top bar (1 is opaque)"),
    "popup_opacity": Spec(_opacity, "0 to 1",
                          "Opacity of popup menus, quick settings and the calendar (1 is opaque)"),
    "floating_panel": Spec(_boolean, "yes, no",
                           "Float the top bar as a rounded bar, docked while a window is near"),
    "panel_gap": Spec(_pixels(12), "0 to 12", "Gap around the floating bar, in pixels"),
    "panel_radius": Spec(_radius, "round, or 0 to 100", "Corner radius of the floating bar, in pixels",
                         none_as="round"),
    "docked_panel_opacity": Spec(_docked_opacity, "same, or 0 to 1",
                                 "Opacity of the floating bar while docked; 'same' keeps that of the top bar",
                                 none_as="same"),
    "dock_like_panel": Spec(_boolean, "yes, no",
                            "Give the dock of Dash to Dock or Ubuntu Dock the color and opacity of the top bar"),
    "dock_radius": Spec(_dock_radius, f"{DOCK}, {ROUND}, or 0 to 100",
                        "Corner radius of the dock of Dash to Dock; 'round' is as round as the floating top bar, "
                        f"'{DOCK}' keeps the radius Dash to Dock draws",
                        none_as=DOCK),
    "show_apps_icon": Spec(_icon_file, f"{ICON_DEFAULT}, or an .svg or .png file",
                           "Icon of the Show Applications button of the dock of Dash to Dock; "
                           f"{ICON_FLAVOR} in the name stands for the flavor in use, so that there can be one for "
                           f"each; '{ICON_DEFAULT}' keeps the one GNOME draws",
                           none_as=ICON_DEFAULT),
    "blur": Spec(_blur, "yes, no",
                 "Blur the desktop behind the top bar, popup menus, the overview and the dock"),
    "blur_radius": Spec(_pixels(100), "0 to 100", "How far the blur reaches, in pixels"),
    "blur_background": Spec(_boolean, "yes, no",
                            "Blur the wallpaper behind the overview and on the lock screen; with this off "
                            "they keep what GNOME gives them"),
    "blur_background_radius": Spec(_pixels(100), "0 to 100",
                                   "How far the blur of that wallpaper reaches, in pixels"),
    "shell_version": Spec(_shell_version, f"{AUTO}, or a version such as 49.2",
                          f"GNOME Shell version to build the theme for; '{AUTO}' detects it"),
}

# Asked by `configure` only when the floating bar is on
FLOATING_ONLY = ("panel_gap", "panel_radius", "docked_panel_opacity")
# Asked by `configure` only when there is a blur to size
BLUR_ONLY = ("blur_radius", "blur_background", "blur_background_radius")


# --- How the preferences are shown by the terminal and the window ---------------

SWITCH, CHOICE, TEXT = "switch", "choice", "text"


@dataclass(frozen=True)
class Field:
    """A preference as an interface shows it: where, as what, and when."""
    name: str
    spec: Spec
    group: str
    kind: str                      # SWITCH, CHOICE or TEXT
    choices: tuple = ()            # the words of a CHOICE; for a TEXT, the ones that are also allowed
    requires: Optional[str] = None  # shown only while this switch is on
    live: bool = False             # changes in the running extension, with no apply

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").capitalize()

    @property
    def option(self) -> str:
        return _option_name(self.name)


def _option_name(name: str) -> str:
    return "--" + name.replace("_", "-")


# The groups, in the order shown, and the preferences in each
GROUPS = (
    ("Colors", ("flavor", "accent", "accent_selection")),
    ("Top bar", ("panel_opacity", "popup_opacity", "floating_panel", "panel_gap", "panel_radius",
                 "docked_panel_opacity")),
    ("Dock", ("dock_like_panel", "dock_radius", "show_apps_icon")),
    ("Blur", ("blur", "blur_radius", "blur_background", "blur_background_radius")),
    ("Install", ("shell_theme", "gtk_theme", "flatpak", "shell_version")),
)
_CHOICES = {
    "flavor": palette.DARK_FLAVORS,
    "accent": (FOLLOW, *palette.ACCENTS),
}
_REQUIRES = {name: "floating_panel" for name in FLOATING_ONLY} | {name: "blur" for name in BLUR_ONLY}
# What the extensions change while they run, once they read their own settings
_LIVE = frozenset()


def all_fields() -> list:
    """Every preference, grouped and in the order an interface shows them."""
    result = []
    for group, names in GROUPS:
        for name in names:
            spec = SPECS[name]
            if name in _CHOICES:
                kind = CHOICE
            elif spec.values == "yes, no":
                kind = SWITCH
            else:
                kind = TEXT
            result.append(Field(name, spec, group, kind, tuple(_CHOICES.get(name, ())),
                                _REQUIRES.get(name), name in _LIVE))
    return result


def visible(field: Field, preferences) -> bool:
    """Whether a field is worth showing: the ones that depend on a switch are not while it is off."""
    return field.requires is None or bool(getattr(preferences, field.requires))


@dataclass
class Preferences:
    flavor: str = "mocha"
    accent: str = FOLLOW
    shell_theme: bool = True
    gtk_theme: bool = True
    flatpak: bool = False
    accent_selection: bool = False
    panel_opacity: float = 1.0
    popup_opacity: float = 1.0
    floating_panel: bool = False
    panel_gap: int = 6
    panel_radius: Optional[int] = None
    docked_panel_opacity: Optional[float] = None
    dock_like_panel: bool = False
    dock_radius: Optional[Union[int, str]] = None
    show_apps_icon: Optional[str] = None
    blur: bool = False
    blur_radius: int = 32
    blur_background: bool = True
    blur_background_radius: int = 32
    shell_version: str = AUTO

    def set(self, name: str, text: str):
        """Set a preference from its text form, checking it."""
        try:
            setattr(self, name, SPECS[name].parse(text))
        except PreferenceError as e:
            raise PreferenceError(f"{name.replace('_', '-')}: {e} (got '{text}')") from None

    def text(self, name: str) -> str:
        """A preference in the form it is typed and stored in."""
        value = getattr(self, name)
        if value is None:
            return SPECS[name].none_as
        if isinstance(value, bool):
            return "yes" if value else "no"
        return f"{value:g}" if isinstance(value, float) else str(value)

    @property
    def follows_picker(self) -> bool:
        return self.accent == FOLLOW


assert [f.name for f in fields(Preferences)] == list(SPECS)

SECTION = "preferences"
HEADER = ("# Preferences of gattuccino. Change them with `gattuccino configure`,\n"
          "# or edit this file and run `gattuccino apply`.\n\n")


def load(path: str) -> Preferences:
    """Read the preferences file; missing entries keep their defaults."""
    preferences = Preferences()
    if not os.path.exists(path):
        return preferences
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error as e:
        raise PreferenceError(f"{path} cannot be read: {e}") from None
    if parser.has_section(SECTION):
        for name, text in parser.items(SECTION):
            if name == "blur_overview":
                name = "blur_background"  # written by an earlier version: it was the overview alone
            if name not in SPECS:
                raise PreferenceError(f"{path}: unknown preference '{name}'")
            if name == "show_apps_icon":
                # A file that has gone since it was chosen is not a reason to stop
                # here: it would make `configure` unable to choose another one.
                # `apply` says it is missing.
                value = text.strip()
                preferences.show_apps_icon = (
                    None if value.lower() in ("", ICON_DEFAULT) else os.path.abspath(os.path.expanduser(value)))
                continue
            if name == "flavor" and text.strip().lower() == palette.LIGHT_FLAVOR:
                continue  # written by an earlier version: latte now comes with every dark flavor
            preferences.set(name, text)
    return preferences


def save(preferences: Preferences, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(HEADER + f"[{SECTION}]\n")
        for name, spec in SPECS.items():
            f.write(f"# {spec.help} ({spec.values})\n{name} = {preferences.text(name)}\n")
