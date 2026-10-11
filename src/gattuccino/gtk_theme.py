"""Generates the colors for GTK applications.

There is no GTK theme here: the files recolor Adwaita, through the color
variables libadwaita exposes for that (and the named colors adw-gtk3 shares
with it for GTK 3 applications).

Each folder gets the colors of both flavors, Latte for the light style and
the chosen dark flavor for the dark one, each in a file of its own
(`gattuccino-FLAVOR.css`), and the accent alone in
`gattuccino-accent.css`. `gtk.css` only imports the flavor of the
current style and the accent. So when the style or the accent changes in
Settings, the catppuccin-accent extension rewrites these two small files and
touches nothing else.

`gattuccino-selection.css` is the exception to "no GTK theme here": with
the accent_selection preference it holds a handful of rules that give selected
sidebar rows and highlighted menu items the accent color, which GNOME tints
with the text color instead (GTK 3 gets everything but the selected row: it
has no `:selected` to match one with). The flavor files import it, not
gtk.css, because those are the files the extension never rewrites: so the
rules stay put, and the extension needs to know nothing about them.
"""

from . import palette

ACCENT_FILE = "gattuccino-accent.css"
SELECTION_FILE = "gattuccino-selection.css"

# First line of every file written here: how install and uninstall tell their
# own files from a gtk.css you wrote yourself.
MARKER = "/* gattuccino:"
# First line as written by an earlier version, under this project's old name:
# a file that still starts with this is recognized as this project's own too.
LEGACY_MARKER = "/* gnome-catppuccin:"


def _colors(flavor: str):
    """libadwaita's color variables, grouped, with their Catppuccin values."""
    c = lambda name: palette.color(flavor, name)  # noqa: E731
    tint = lambda alpha: palette.rgba(flavor, "text", alpha)  # noqa: E731
    return [
        ("Destructive, success, warning, error", [
            ("destructive-bg-color", c("red")), ("destructive-fg-color", c("base")), ("destructive-color", c("red")),
            ("success-bg-color", c("green")), ("success-fg-color", c("base")), ("success-color", c("green")),
            ("warning-bg-color", c("yellow")), ("warning-fg-color", c("base")), ("warning-color", c("yellow")),
            ("error-bg-color", c("red")), ("error-fg-color", c("base")), ("error-color", c("red")),
        ]),
        ("Windows and content: base", [
            ("window-bg-color", c("base")), ("window-fg-color", c("text")),
            ("view-bg-color", c("base")), ("view-fg-color", c("text")),
            ("dialog-bg-color", c("base")), ("dialog-fg-color", c("text")),
        ]),
        ("Header bars and sidebars: mantle, crust", [
            ("headerbar-bg-color", c("mantle")), ("headerbar-fg-color", c("text")),
            ("headerbar-border-color", c("text")), ("headerbar-backdrop-color", c("base")),
            ("sidebar-bg-color", c("mantle")), ("sidebar-fg-color", c("text")),
            ("sidebar-backdrop-color", c("mantle")),
            ("secondary-sidebar-bg-color", c("crust")), ("secondary-sidebar-fg-color", c("text")),
            ("secondary-sidebar-backdrop-color", c("crust")),
            ("overview-bg-color", c("mantle")), ("overview-fg-color", c("text")),
        ]),
        ("Raised elements", [
            ("popover-bg-color", c("surface0") if palette.DARK[flavor] else c("base")),
            ("popover-fg-color", c("text")),
            ("thumbnail-bg-color", c("surface0")), ("thumbnail-fg-color", c("text")),
            ("card-bg-color", tint(0.08)), ("card-fg-color", c("text")),
            ("active-toggle-bg-color", tint(0.2)), ("active-toggle-fg-color", c("text")),
        ]),
    ]


def flavor_file(flavor: str) -> str:
    return f"gattuccino-{flavor}.css"


# gtk.css and the two accent files have exactly the text the catppuccin-accent
# extension writes (see its extension.js): it reads back from their first line
# what they are for.

def gtk_css(dark_flavor: str, dark: bool) -> str:
    """gtk.css, the same in both folders: the flavor of the current style, and the accent."""
    flavor = dark_flavor if dark else palette.LIGHT_FLAVOR
    return (f"{MARKER} style (light={palette.LIGHT_FLAVOR}, dark={dark_flavor})\n"
            " * Written by gattuccino, and by its Catppuccin Accent extension whenever\n"
            " * the style changes in Settings. Edits to this file are overwritten. */\n"
            "\n"
            f'@import url("{flavor_file(flavor)}");\n'
            f'@import url("{ACCENT_FILE}");\n')


def _header(flavor: str, what: str) -> str:
    style = "dark" if palette.DARK[flavor] else "light"
    return (f"{MARKER} Catppuccin {flavor.capitalize()} for {what}.\n"
            f" * Recolors the Adwaita {style} style. Written by gattuccino: edits are\n"
            " * overwritten the next time it is applied. */\n")


def _selection_import(selection: bool) -> str:
    """The flavor files pull in the selection rules; GTK resolves the colors they
    name from the accent file, which gtk.css imports after this one."""
    return f'\n@import url("{SELECTION_FILE}");\n' if selection else ""


def gtk4_css(flavor: str, picker_swatches: bool, selection: bool) -> str:
    """Colors of a flavor for ~/.config/gtk-4.0 (GTK 4 and libadwaita applications)."""
    css = _header(flavor, "GTK 4 / libadwaita applications") + _selection_import(selection) + "\n:root {\n"
    if picker_swatches:
        css += "  /* Swatches of the accent picker in Settings > Appearance */\n"
        for gnome_accent, accent in palette.SETTINGS_ACCENTS.items():
            note = "" if gnome_accent == accent else f" /* {accent} */"
            css += f"  --accent-{gnome_accent}: {palette.color(flavor, accent)};{note}\n"
        css += "\n"
    groups = _colors(flavor)
    css += "\n".join(
        f"  /* {title} */\n" + "".join(f"  --{name}: {value};\n" for name, value in colors)
        for title, colors in groups)
    css += "}\n\n/* The same colors under their older names, for applications built on libadwaita before 1.6 */\n"
    css += "".join(f"@define-color {name.replace('-', '_')} {value};\n"
                   for _, colors in groups for name, value in colors)
    return css


def gtk3_css(flavor: str, selection: bool) -> str:
    """Colors of a flavor for ~/.config/gtk-3.0 (GTK 3 applications using the adw-gtk3 theme)."""
    theme = "adw-gtk3-dark" if palette.DARK[flavor] else "adw-gtk3"
    css = _header(flavor, f"GTK 3 applications using the {theme} theme") + _selection_import(selection) + "\n"
    css += "\n".join(
        f"/* {title} */\n" + "".join(f"@define-color {name.replace('-', '_')} {value};\n" for name, value in colors)
        for title, colors in _colors(flavor))
    return css


def _accent_header(flavor: str, setting: str) -> str:
    """`setting` is the accent preference: "follow", or the accent that is always used."""
    return (f"{MARKER} accent (flavor={flavor}, accent={setting})\n"
            " * Written by gattuccino, and by its Catppuccin Accent extension whenever\n"
            " * the style or the accent color changes in Settings. Edits to this file are overwritten. */\n")


def _accent_named_colors(flavor: str, accent: str) -> str:
    color, foreground = palette.color(flavor, accent), palette.color(flavor, "base")
    return (f"@define-color accent_bg_color {color};\n"
            f"@define-color accent_fg_color {foreground};\n"
            f"@define-color accent_color {color};\n")


def gtk4_accent_css(flavor: str, accent: str, setting: str) -> str:
    color, foreground = palette.color(flavor, accent), palette.color(flavor, "base")
    return (f"{_accent_header(flavor, setting)}\n"
            ":root {\n"
            f"  --accent-bg-color: {color};\n"
            f"  --accent-fg-color: {foreground};\n"
            f"  --accent-color: {color};\n"
            "}\n\n"
            f"{_accent_named_colors(flavor, accent)}")


def gtk3_accent_css(flavor: str, accent: str, setting: str) -> str:
    return f"{_accent_header(flavor, setting)}\n{_accent_named_colors(flavor, accent)}"


# --- Selected rows and highlighted menu items ---------------------------------

# The only rules this project writes. GNOME tints both with the text color
# (`color-mix(in srgb, currentColor 10%, transparent)` in libadwaita,
# `alpha(currentColor,0.1)` in adw-gtk3), so no variable can recolor them.
#
# The accent is named indirectly, through the GTK 4 variables and the GTK 3
# named colors that the accent file defines, so these files stay the same
# whatever the flavor and the accent are, and the catppuccin-accent extension
# never has to rewrite them. GTK resolves both lazily, so it does not matter
# that the accent file is imported after the flavor file that pulls this one in.

def _selection_header(what: str, covers: str) -> str:
    return (f"{MARKER} selection\n"
            f" * The accent color for {covers} in {what},\n"
            " * which GNOME tints with the text color instead. Written by gattuccino:\n"
            " * edits are overwritten the next time it is applied, and the file is removed\n"
            " * when accent-selection is off. */\n")


# Hover and pressed states have to be given too: this file outranks the theme,
# so the theme's own `:selected:hover` no longer shows through.
GTK4_SELECTION = """
/* Sidebar rows: Nautilus's places, the lists in Settings, and anything else
 * using libadwaita's .navigation-sidebar */
.navigation-sidebar row:selected,
.navigation-sidebar child:selected,
.navigation-sidebar flowboxchild:selected {
  background-color: var(--accent-bg-color);
  color: var(--accent-fg-color);
}

.navigation-sidebar row:selected:hover,
.navigation-sidebar child:selected:hover,
.navigation-sidebar flowboxchild:selected:hover {
  background-color: color-mix(in srgb, var(--accent-fg-color) 12%, var(--accent-bg-color));
}

.navigation-sidebar row:selected:active,
.navigation-sidebar child:selected:active,
.navigation-sidebar flowboxchild:selected:active {
  background-color: color-mix(in srgb, var(--accent-fg-color) 22%, var(--accent-bg-color));
}

/* Hovering a row that is not selected: a light tint of the accent, where
 * Adwaita uses the text color (7% of it, and 16% while pressed). */
.navigation-sidebar row.activatable:not(:selected):hover,
.navigation-sidebar child.activatable:not(:selected):hover,
.navigation-sidebar flowboxchild:not(:selected):hover,
.navigation-sidebar row.activatable:not(:selected).has-open-popup,
.navigation-sidebar child.activatable:not(:selected).has-open-popup,
.navigation-sidebar flowboxchild:not(:selected).has-open-popup {
  background-color: color-mix(in srgb, var(--accent-bg-color) 20%, transparent);
}

.navigation-sidebar row.activatable:not(:selected):active,
.navigation-sidebar child.activatable:not(:selected):active,
.navigation-sidebar flowboxchild:not(:selected):active {
  background-color: color-mix(in srgb, var(--accent-bg-color) 32%, transparent);
}

/* Menu items. Their check marks, radios and arrows inherit the color, so they
 * follow on their own. :selected is the keyboard-highlighted item. */
popover.menu modelbutton:not(:disabled):hover,
popover.menu modelbutton:not(:disabled):selected {
  background-color: var(--accent-bg-color);
  color: var(--accent-fg-color);
}

popover.menu modelbutton:not(:disabled):active {
  background-color: color-mix(in srgb, var(--accent-fg-color) 22%, var(--accent-bg-color));
  color: var(--accent-fg-color);
}
"""

# GTK 3 has no `:selected` to match a *selected* list row with (its matchable
# states are :hover, :active, :checked, :focus, :backdrop and :disabled), so a
# selected row there keeps the plain sidebar color adw-gtk3 gives it. Hovering
# is `:hover` in both, so that half works the same as in GTK 4.
GTK3_SELECTION = """
/* Menu items, of both kinds: GtkMenu, and the popovers that replaced it.
 * Their check marks and radios inherit the color, so they follow on their own. */
menu menuitem:hover,
.menu menuitem:hover,
.context-menu menuitem:hover,
modelbutton.flat:hover,
.menuitem.button.flat:hover {
  background-color: @accent_bg_color;
  color: @accent_fg_color;
}

/* Hovering a sidebar row: a light tint of the accent */
.sidebar row.activatable:hover,
placessidebar row.activatable:hover,
stacksidebar row.activatable:hover {
  background-color: alpha(@accent_bg_color, 0.2);
}

.sidebar row.activatable:active,
placessidebar row.activatable:active,
stacksidebar row.activatable:active {
  background-color: alpha(@accent_bg_color, 0.32);
}
"""


def gtk4_selection_css() -> str:
    return _selection_header("GTK 4 / libadwaita applications",
                             "selected and hovered sidebar rows and highlighted menu items") + GTK4_SELECTION


def gtk3_selection_css() -> str:
    return _selection_header("GTK 3 applications using the adw-gtk3 theme",
                             "hovered sidebar rows and highlighted menu items") + GTK3_SELECTION


def files(dark_flavor: str, dark: bool, accent: str, setting: str, selection: bool):
    """Everything to write, as {folder: {file name: contents}}.

    `dark` tells which style is in use now, `accent` is the accent in use now,
    `setting` the accent preference ("follow" or an accent name), and
    `selection` whether sidebar rows and menu items get the accent.
    """
    flavors = (palette.LIGHT_FLAVOR, dark_flavor)
    current = dark_flavor if dark else palette.LIGHT_FLAVOR
    swatches = setting == "follow"
    return {
        "gtk-4.0": {
            "gtk.css": gtk_css(dark_flavor, dark),
            **{flavor_file(f): gtk4_css(f, swatches, selection) for f in flavors},
            ACCENT_FILE: gtk4_accent_css(current, accent, setting),
            **({SELECTION_FILE: gtk4_selection_css()} if selection else {}),
        },
        "gtk-3.0": {
            "gtk.css": gtk_css(dark_flavor, dark),
            **{flavor_file(f): gtk3_css(f, selection) for f in flavors},
            ACCENT_FILE: gtk3_accent_css(current, accent, setting),
            **({SELECTION_FILE: gtk3_selection_css()} if selection else {}),
        },
    }
