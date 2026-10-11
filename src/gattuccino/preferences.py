"""The preferences: what they are, how they are checked, where they are kept."""

import configparser
import os
from dataclasses import dataclass, fields
from typing import Optional

from . import palette

HELP_ACCENT_SELECTION = (
    "Use the accent color for selected sidebar rows and highlighted menu items in "
    "applications, where GNOME uses a shade of the text color"
)

FOLLOW = "follow"  # accent: whatever is picked in Settings > Appearance
AUTO = "auto"      # shell_version: the installed GNOME Shell


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
    "shell_version": Spec(_shell_version, f"{AUTO}, or a version such as 49.2",
                          f"GNOME Shell version to build the theme for; '{AUTO}' detects it"),
}

# Asked by `configure` only when the floating bar is on
FLOATING_ONLY = ("panel_gap", "panel_radius", "docked_panel_opacity")


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
            if name not in SPECS:
                raise PreferenceError(f"{path}: unknown preference '{name}'")
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
