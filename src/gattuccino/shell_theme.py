"""Builds the GNOME Shell theme.

The theme is not written from scratch: it is GNOME Shell's own stylesheet,
recompiled with the Catppuccin palette in place of Adwaita's and a few
targeted edits. Each edit below checks that the line it changes is there, so
a GNOME Shell release that moved things fails loudly instead of producing a
half-themed stylesheet.
"""

import glob
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

from . import palette

# Dropped in every theme folder this project creates, so that installing and
# uninstalling only ever touch its own folders.
MARKER = ".gattuccino"
# Dropped by an earlier version, under this project's old name: a theme folder
# that still carries this one is recognized as this project's own too, so it
# gets cleaned up on the next apply instead of being left behind.
LEGACY_MARKERS = (".gnome-catppuccin",)


class BuildError(Exception):
    pass


@dataclass
class ShellOptions:
    panel_opacity: Optional[float] = None    # None: opaque
    popup_opacity: Optional[float] = None    # None: opaque
    floating_panel: bool = False
    panel_gap: int = 6
    panel_radius: Optional[int] = None       # None: fully round
    docked_panel_opacity: Optional[float] = None  # None: same as the panel
    dock_like_panel: bool = False
    accent_selection: bool = False


def theme_name(flavor: str, accent: str) -> str:
    """Folder name of a theme. The catppuccin-accent extension switches between
    themes whose names differ only by the accent at the end."""
    return f"gattuccino-{flavor}-{accent}"


# --- Sass ---------------------------------------------------------------

def find_compiler():
    """Name of the available Sass compiler, or None."""
    try:
        import sass  # noqa: F401  (python3-libsass)
        return "libsass"
    except ImportError:
        return "sassc" if shutil.which("sassc") else None


NO_COMPILER = ("No Sass compiler found. Install sassc (packaged by every distribution) "
               "or the Python module: pip install libsass")


def require_compiler():
    if not find_compiler():
        raise BuildError(NO_COMPILER)


# Both compilers are LibSass and give the same output at the same precision;
# 10 digits is what GNOME Shell's own build (sassc) uses.
PRECISION = 10


def compile_scss(path: str) -> str:
    compiler = find_compiler()
    if compiler == "libsass":
        import sass
        try:
            return sass.compile(filename=path, precision=PRECISION)
        except sass.CompileError as e:
            raise BuildError(f"Sass could not compile the stylesheet:\n{e}") from e
    if compiler == "sassc":
        result = subprocess.run(["sassc", "--precision", str(PRECISION), path],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise BuildError(f"sassc could not compile the stylesheet:\n{result.stderr}")
        return result.stdout
    raise BuildError(NO_COMPILER)


# --- Edits to GNOME Shell's stylesheets ---------------------------------

def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _set_variable(path: str, variable: str, value: str):
    """Redefine a top-level `$variable: ...;` line."""
    text, n = re.subn(rf"(?m)^\${re.escape(variable)}:.*$", lambda _: f"${variable}: {value};", _read(path))
    if n != 1:
        raise BuildError(f"Expected one ${variable} definition in {os.path.basename(path)}, found {n}. "
                         "This GNOME Shell version is not supported.")
    _write(path, text)


def _replace_once(path: str, old: str, new: str):
    text = _read(path)
    if text.count(old) != 1:
        raise BuildError(f"Expected one {old!r} in {os.path.basename(path)}, found {text.count(old)}. "
                         "This GNOME Shell version is not supported.")
    _write(path, text.replace(old, new))


def _replace_if_present(path: str, old: str, new: str):
    """For cosmetic adjustments that a GNOME Shell version may not need."""
    text = _read(path)
    if old in text:
        _write(path, text.replace(old, new))


def _palette_scss(flavor: str) -> str:
    """GNOME Shell's palette file, with Catppuccin colors behind GNOME's names."""
    dark = palette.DARK[flavor]
    lines = [f"// Catppuccin {flavor}"]
    lines += [f"$ctp-{name}: {value};" for name, value in palette.FLAVORS[flavor].items()]

    mapping = {
        "blue": ["sky", "sapphire", "sapphire", "blue", "blue"],
        "green": ["teal", "green", "green", "green", "green"],
        "yellow": ["yellow", "yellow", "yellow", "yellow", "peach"],
        "orange": ["peach"] * 5,
        "red": ["red"] * 5,
        "purple": ["mauve"] * 5,
        "brown": ["maroon"] * 5,
    }
    if dark:
        # light_1 is the text color, dark_5 the darkest background
        mapping["light"] = ["text", "subtext1", "subtext0", "overlay2", "overlay1"]
        mapping["dark"] = ["surface2", "surface1", "surface0", "base", "crust"]
    else:
        # light_1 is the lightest background, dark_5 the text color
        mapping["light"] = ["base", "mantle", "crust", "surface0", "surface1"]
        mapping["dark"] = ["subtext0", "subtext1", "text", "text", "text"]

    lines.append("\n// GNOME color palette, mapped to the above")
    for gnome_name, names in mapping.items():
        lines += [f"${gnome_name}_{i}: $ctp-{name};" for i, name in enumerate(names, start=1)]
    return "\n".join(lines) + "\n"


def _apply_palette(sass_dir: str, flavor: str):
    _write(f"{sass_dir}/_palette.scss", _palette_scss(flavor))

    defaults = f"{sass_dir}/_default-colors.scss"
    _write(defaults, '@import "_palette.scss";\n' + _read(defaults))
    if palette.DARK[flavor]:
        # "dark" is the background, "light" the text of the parts of the shell
        # that are always dark (overview, on-screen displays)
        _set_variable(defaults, "_base_color_dark", "$ctp-base")
        _set_variable(defaults, "_base_color_light", palette.color("latte", "base"))
    else:
        # "light" is the background of panel and popups, with cards one step
        # lighter ($light_1); "dark" is the text, and the background of the
        # parts of the shell that are always dark
        _set_variable(defaults, "_base_color_dark", "$ctp-text")
        _set_variable(defaults, "_base_color_light", "$ctp-mantle")
    # Adwaita uses two colors from outside its palette here
    _set_variable(defaults, "warning_bg_color", "$yellow_5")
    _set_variable(defaults, "warning_fg_color", "transparentize($dark_5, .2)")
    _set_variable(f"{sass_dir}/_colors.scss", "bg_color",
                  "if($variant == 'light', $_base_color_light, $_base_color_dark)")


def _apply_accent(theme_src: str, flavor: str, accent: str):
    """Bake a Catppuccin accent into the theme.

    GNOME Shell normally resolves `-st-accent-color` at runtime from the accent
    picked in Settings, and that is always one of GNOME's own colors. To get a
    Catppuccin accent, every use of it is replaced with a palette color.
    """
    sass_dir = f"{theme_src}/gnome-shell-sass"
    with open(f"{sass_dir}/_palette.scss", "a", encoding="utf-8") as f:
        # What sits on an accent is the base color in every flavor: dark on
        # the pastel accents of the dark flavors, light on Latte's.
        f.write(f"\n// Accent\n$accent: $ctp-{accent};\n$accent_fg: $ctp-base;\n")

    found = False
    for path in glob.glob(f"{theme_src}/**/*.scss", recursive=True):
        text = _read(path)
        new = text.replace("-st-accent-fg-color", "$accent_fg").replace("-st-accent-color", "$accent")
        if new != text:
            found = True
            _write(path, new)
    if not found:
        raise BuildError("This GNOME Shell version has no accent color support. "
                         "This GNOME Shell version is not supported.")

    if not palette.DARK[flavor]:
        return  # Latte's accents are as dark as GNOME's own: its rules fit as they are

    # GNOME lightens its dark, saturated accents for focus rings, links and
    # borders on dark backgrounds. A pastel accent is light enough already, and
    # lightening it further washes it out to near white.
    _set_variable(f"{sass_dir}/_default-colors.scss", "accent_color", "$accent")
    _set_variable(f"{sass_dir}/_default-colors.scss", "link_color", "$accent")
    _set_variable(f"{sass_dir}/_colors.scss", "accent_borders_color", "$light_1")

    # A few widgets assume a dark accent and draw white on top of it.
    # "Today" in the calendar: use the dark event dot
    _replace_if_present(f"{sass_dir}/widgets/_calendar.scss",
                        'calendar-today.svg") !important', 'calendar-today-light.svg") !important')
    # Handle of a switch that is on
    _replace_if_present(f"{sass_dir}/widgets/_switches.scss",
                        "background: white;", "background: $accent_fg;")
    # Latched keys (shift, ctrl...) of the on-screen keyboard
    _replace_if_present(f"{sass_dir}/widgets/_keyboard.scss",
                        "background-color: $accent;", "background-color: $accent; color: $accent_fg;")


# The shell's counterpart of the accent-selection rules for applications.
# GNOME draws every highlight here as a lightened or darkened shade of
# whatever is behind it; these edits make that shade a tint of the accent, and
# give the two states that mean "this one" (a highlighted menu item, a selected
# tile) the accent itself.
#
# Four edits to _drawing.scss cover nearly everything, because almost all of
# the shell highlights through one of its three mixins; the window switcher
# styles its own selection and needs a fifth. `st-mix` and
# `st-transparentize` are GNOME Shell's own functions, resolved when it loads
# the stylesheet, so an accent baked in here still composites over whatever is
# behind the widget.

# How much accent a hovered and a pressed surface get, as a percentage
HOVER_TINT = 20
ACTIVE_TINT = 32


def _apply_accent_selection(sass_dir: str):
    drawing = f"{sass_dir}/_drawing.scss"

    # 1. Menu items, the one place with both a hover and a keyboard-selected
    #    state. `:active` stays ahead of `:hover` as in the original, so a
    #    pressed item that is hovered still shows the hover color.
    _replace_once(
        drawing,
        "  &:hover, &:selected, &:checked { @include button(hover, $c:$bg, $style: flat);}",
        "  // gattuccino: the accent for the highlighted item\n"
        "  &:hover, &:selected { background-color: $accent; color: $accent_fg;}\n"
        f"  &:hover:active, &:selected:active {{ background-color: st-mix($accent_fg, $accent, {ACTIVE_TINT}%); "
        "color: $accent_fg;}\n"
        "  // an expanded submenu header stays neutral: it is not a highlight\n"
        "  &:checked { @include button(hover, $c:$bg, $style: flat);}")

    # 2. Every button, flat or raised: panel menu buttons, quick settings,
    #    calendar days, overview tiles, search results, dialog lists, the dock.
    #    The dialog, lockscreen and notification styles set these again further
    #    down and so keep GNOME's own translucent shades.
    _replace_once(
        drawing,
        "  $hover_button_bg_color: if($variant == 'light', st-darken($button_bg_color, $hover_factor), "
        "st-lighten($button_bg_color, $hover_factor));\n"
        "  $active_button_bg_color: if($variant == 'light', st-darken($button_bg_color, $active_factor), "
        "st-lighten($button_bg_color, $active_factor));",
        "  // gattuccino: a tint of the accent, where GNOME lightens or darkens\n"
        f"  $hover_button_bg_color: st-mix($accent, $button_bg_color, {HOVER_TINT}%);\n"
        f"  $active_button_bg_color: st-mix($accent, $button_bg_color, {ACTIVE_TINT}%);")

    # 3. A selected or highlighted tile takes the accent itself: the window
    #    switcher's current window, and highlighted icons in the app grid.
    #    Both branches of the mixin, raised and flat.
    for extra in ("", "$style: flat, "):
        _replace_once(
            drawing,
            "    &:highlighted,&:selected,\n"
            f"    &:checked {{ @include button(checked, $tc:$fg, $c:$bg, {extra}$always_dark: $system);}}",
            "    // gattuccino: the accent for a selected tile\n"
            "    &:highlighted,&:selected,\n"
            "    &:checked { background-color: $accent; color: $accent_fg;}")

    # 4. The top bar, which mixes its own translucent fills rather than going
    #    through button(). Translucent so a translucent panel stays so.
    _replace_once(
        drawing,
        "  $hover_fill:        transparentize($fg, .83);\n"
        "  $active_fill:       transparentize($fg, .72);\n"
        "  $active_hover_fill: transparentize($fg, .68);",
        "  // gattuccino: tints of the accent, where GNOME tints with the text color\n"
        "  $hover_fill:        transparentize($accent, .75);\n"
        "  $active_fill:       transparentize($accent, .6);\n"
        "  $active_hover_fill: transparentize($accent, .55);")

    # 5. The window switcher brightens its selected window itself, after the
    #    tile mixin has run, so it needs saying again here.
    _replace_once(
        f"{sass_dir}/widgets/_switcher-popup.scss",
        "    // brighter than normal selected style\n"
        "    &:selected {\n"
        "      background-color: transparentize($osd_fg_color, 0.8);\n"
        "    }",
        "    // gattuccino: the accent for the selected window\n"
        "    &:selected {\n"
        "      background-color: $accent;\n"
        "      color: $accent_fg;\n"
        "    }")


def _transparent(color: str, opacity: float) -> str:
    return f"transparentize({color}, {round(1 - opacity, 4):g})"


def _apply_panel_opacity(sass_dir: str, opacity: float):
    # The panel is already transparent in the overview and on the lock screen
    _replace_once(f"{sass_dir}/widgets/_panel.scss", "background-color: $panel_bg_color;",
                  f"background-color: {_transparent('$panel_bg_color', opacity)};")


def _apply_popup_opacity(sass_dir: str, opacity: float):
    # Background shared by panel menus, quick settings, the calendar and right-click menus
    _replace_once(f"{sass_dir}/widgets/_popovers.scss", "background-color: $bg_color;",
                  f"background-color: {_transparent('$bg_color', opacity)};")

    # Flat buttons (calendar days, icon buttons...) are painted in the color of
    # whatever is behind them, which shows as solid patches on a translucent
    # popup. Leave them unpainted until they are hovered or pressed.
    path = f"{sass_dir}/_drawing.scss"
    text = _read(path)
    for variable in ("button_bg_color", "insensitive_button_bg_color"):
        text, n = re.subn(rf"(?m)^(\s*)background-color: \${variable};$",
                          rf"\1background-color: if($style == 'flat', transparent, ${variable});", text)
        if n != 1:
            raise BuildError(f"Expected one 'background-color: ${variable};' in _drawing.scss, found {n}. "
                             "This GNOME Shell version is not supported.")
    _write(path, text)


def _apply_floating_panel(sass_dir: str, options: ShellOptions):
    """Style the panel for the two states set by the floating-panel extension.

    A theme cannot know where windows are. The extension puts the class
    `floating-panel` on the panel while no window is near, and `docked-panel`
    while one is. With the extension disabled the panel has neither class and
    keeps its normal look.
    """
    gap = options.panel_gap
    radius = "$forced_circular_radius" if options.panel_radius is None else f"{options.panel_radius}px"
    style = f"""
// Floating panel: no window is near (class set by the floating-panel extension)
#panel.floating-panel {{
  margin: {gap}px {gap}px 0 {gap}px;
  border-radius: {radius};
}}
"""
    if options.docked_panel_opacity is not None:
        style += f"""
// Docked panel: a window is maximized or close (class set by the floating-panel extension)
#panel.docked-panel {{
  background-color: {_transparent('$panel_bg_color', options.docked_panel_opacity)};

  // the overview keeps its transparent panel
  &:overview {{ background-color: transparent; }}
}}
"""
    with open(f"{sass_dir}/widgets/_panel.scss", "a", encoding="utf-8") as f:
        f.write(style)


def _apply_dock(sass_dir: str, options: ShellOptions):
    """Give the dock of Dash to Dock (and Ubuntu Dock, which is the same
    extension) the color and opacity of the top bar.

    Left alone, the dock looks like the dash of the overview. This restyles it
    only inside the extension's container, so the overview's own dash is
    unchanged.
    """
    path = f"{sass_dir}/widgets/_dash.scss"
    text = _read(path)
    for expected in (".dash-background", ".overview-icon", ".show-apps"):
        if expected not in text:
            raise BuildError(f"Expected {expected} in _dash.scss. This GNOME Shell version is not supported.")

    background = "$panel_bg_color"
    if options.panel_opacity is not None:
        background = _transparent(background, options.panel_opacity)
    _write(path, text + f"""
// Dock of Dash to Dock and Ubuntu Dock: the color and opacity of the top bar.
// The extension's own stylesheet outranks any theme, and keeps its say on the
// hover highlight of the icons and on the separator.
#dashtodockContainer #dash {{
  .dash-background {{ background-color: {background}; }}

  .dash-item-container {{
    // the icons, as above but on the colors of the top bar
    .show-apps,
    .overview-tile {{
      $fg: $panel_fg_color;
      $bg: $panel_bg_color;

      .overview-icon {{
        @include button(normal, $tc:$fg, $c:$bg, $style: flat);
        background-color: transparent;
      }}
      &:focus .overview-icon {{ @include button(focus, $tc:$fg, $c:$bg, $style: flat);}}
      &:hover .overview-icon {{ @include button(hover, $tc:$fg, $c:$bg, $style: flat);}}
      &:active .overview-icon {{ @include button(active, $tc:$fg, $c:$bg, $style: flat);}}
      &:checked .overview-icon {{ @include button(checked, $tc:$fg, $c:$bg, $style: flat);}}
    }}

    .app-grid-running-dot {{ background-color: $panel_fg_color; }}
  }}
}}
""")


# --- The accent in the dock of Dash to Dock -----------------------------

# Written next to the theme's own stylesheet, and loaded by the
# catppuccin-accent extension rather than being part of the theme. Dash to Dock
# states the highlight of a focused and of a hovered icon, and the color of its
# notification counter, in its own stylesheet, and GNOME Shell ranks the
# stylesheet of an extension above every rule of a theme, !important or not (it
# sorts declarations by origin, with extension stylesheets last). So the accent
# has to come from an extension stylesheet too, where !important is what gets
# ahead of another extension: that is why it is used here and nowhere else.
DOCK_STYLESHEET = "gattuccino-dock.css"


def dock_accent_css(flavor: str, accent: str) -> str:
    """The accent in the dock of Dash to Dock (and Ubuntu Dock): a light accent
    on the icon of the application in focus and on the icon under the pointer,
    and the accent itself on the windows and notification counters.

    Every rule is inside the extension's own container, so the dash of the
    overview keeps the colors of the theme.
    """
    color = palette.color(flavor, accent)
    on_accent = palette.color(flavor, "base")
    item = "#dashtodockContainer #dash .dash-item-container"
    return f"""/* gattuccino: dock accent (flavor={flavor}, accent={accent})
 * Written by gattuccino, and loaded by its Catppuccin Accent extension.
 * Not part of the theme: Dash to Dock states these colors in its own
 * stylesheet, which outranks any theme, so they come from an extension
 * stylesheet too, where !important is what gets ahead of it.
 * Edits to this file are overwritten. */

/* The application in focus and the icon under the pointer: a light accent.
   Translucent, so the dock's own background still shows through, and behind an
   application icon the accent next to it reads as a highlight and not as a
   block of color. As in Dash to Dock itself, the two states look the same: it
   is the counter indicator below the icon that says which one has focus. */
{item} .overview-tile.focused .overview-icon,
{item} .overview-tile:hover .overview-icon,
{item} .show-apps:hover .overview-icon {{
  background-color: st-transparentize({color}, 0.7) !important;
}}

/* and a little more of it while pressed */
{item} .overview-tile.focused:active .overview-icon,
{item} .overview-tile:active .overview-icon,
{item} .show-apps:active .overview-icon {{
  background-color: st-transparentize({color}, 0.55) !important;
}}

/* The windows counter indicators: every style of them is drawn in the color of
   the dot it stands in for, so this one rule covers all of them. It needs
   "Customize windows counter indicators" off in the extension's settings. */
{item} .app-grid-running-dot,
{item} .app-well-app-running-dot {{
  background-color: {color} !important;
}}

/* The notification counter */
#dashtodockContainer #dash .notification-badge {{
  background-color: {color} !important;
  color: {on_accent} !important;
}}
"""

# --- Build ---------------------------------------------------------------

def build_css(source_theme_dir: str, flavor: str, accent: str, options: ShellOptions) -> str:
    """Compile the shell stylesheet for one flavor and accent.

    `source_theme_dir` is the data/theme folder of the GNOME Shell sources.
    """
    with tempfile.TemporaryDirectory(prefix="gattuccino-") as work:
        theme_src = f"{work}/theme"
        shutil.copytree(source_theme_dir, theme_src)
        sass_dir = f"{theme_src}/gnome-shell-sass"
        if not os.path.isdir(sass_dir):
            raise BuildError(f"{source_theme_dir} does not look like GNOME Shell's data/theme folder.")

        _apply_palette(sass_dir, flavor)
        _apply_accent(theme_src, flavor, accent)
        if options.accent_selection:
            _apply_accent_selection(sass_dir)
        if options.panel_opacity is not None:
            _apply_panel_opacity(sass_dir, options.panel_opacity)
        if options.popup_opacity is not None:
            _apply_popup_opacity(sass_dir, options.popup_opacity)
        if options.floating_panel:
            _apply_floating_panel(sass_dir, options)
        if options.dock_like_panel:
            _apply_dock(sass_dir, options)

        variant = "dark" if palette.DARK[flavor] else "light"
        return compile_scss(f"{theme_src}/gnome-shell-{variant}.scss")


def write_theme(directory: str, css: str, flavor: str, accent: str, shell_version: str,
                dock_accent: bool = False):
    """Write a theme folder the User Themes extension can load."""
    os.makedirs(f"{directory}/gnome-shell", exist_ok=True)
    _write(f"{directory}/gnome-shell/gnome-shell.css", css)
    if dock_accent:
        _write(f"{directory}/gnome-shell/{DOCK_STYLESHEET}", dock_accent_css(flavor, accent))
    _write(f"{directory}/index.theme",
           "[Desktop Entry]\n"
           "Type=X-GNOME-Metatheme\n"
           f"Name=Gattuccino {flavor.capitalize()} {accent.capitalize()}\n"
           "Comment=GNOME Shell theme with the Catppuccin palette\n"
           "Encoding=UTF-8\n")
    _write(f"{directory}/{MARKER}",
           f"Built by gattuccino from the GNOME Shell {shell_version} stylesheets.\n")
