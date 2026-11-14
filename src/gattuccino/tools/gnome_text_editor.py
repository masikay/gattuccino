"""GNOME Text Editor, which colors text with a GtkSourceView style scheme: the one
named by its `style-scheme` setting, found among the `.xml` files of
`~/.local/share/gtksourceview-5/styles` and the ones that come with it, and, while its
`style-variant` setting is `follow`, the dark or the light variant that the scheme names
for the style of the desktop.

The schemes are the ones of the official Catppuccin port, one for each flavor, unchanged
but for what is said here (see data/tools/gnome-text-editor/SOURCE.md). The port has no
accent: the cursor, where it has rosewater, and the number of the current line, where it
has lavender, are given the accent in use. Two schemes are written from them: `gattuccino`,
of Latte, which names `gattuccino-dark`, of the dark flavor, as its dark variant (and the other
way round), so that the editor changes between them as the style of the desktop is switched,
with no help. `style-scheme` is pointed at the first, and what it was is remembered (in the
state file) to be put back.

Where the editor is told to stay light or dark (`style-variant`) it does, and is said to.
A window that is already open may keep the colors it has until it is opened again.
"""

import os
import re

from .. import palette
from . import DATA, Tool, header, remove_managed, write_managed

THEMES = os.path.join(DATA, "gnome-text-editor", "themes")
SCHEMA = "org.gnome.TextEditor"
LIGHT_ID, DARK_ID = "gattuccino", "gattuccino-dark"
SCHEME = re.compile(r'<style-scheme id="[^"]*" version="1.0" name="[^"]*">')
CURSOR = re.compile(r'(<style name="cursor"\s+foreground=)"rosewater"')
CURRENT_LINE = re.compile(r'(<style name="current-line-number"[^>]*?foreground=)"lavender"')


def theme_file(flavor: str) -> str:
    return os.path.join(THEMES, f"catppuccin-{flavor}.xml")


def scheme_text(flavor: str, accent: str, dark: bool) -> str:
    """The scheme of a flavor, as one of the two: with its own id and name, the variant it names, and the accent."""
    with open(theme_file(flavor), "r", encoding="utf-8") as f:
        declaration, _, rest = f.read().partition("\n")
    ident, name = (DARK_ID, "Gattuccino Dark") if dark else (LIGHT_ID, "Gattuccino")
    variant = ('<property name="variant">dark</property><property name="light-variant">%s</property>' % LIGHT_ID
               if dark else
               '<property name="variant">light</property><property name="dark-variant">%s</property>' % DARK_ID)
    rest = SCHEME.sub(f'<style-scheme id="{ident}" version="1.0" name="{name}">', rest, count=1)
    rest = rest.replace("</description>\n", f"</description>\n  <metadata>{variant}</metadata>\n", 1)
    rest = CURSOR.sub(rf'\1"{accent}"', rest)
    rest = CURRENT_LINE.sub(rf'\1"{accent}"', rest)
    note = (f"<!-- gattuccino: gnome-text-editor scheme (flavor={flavor}, accent={accent}) -->\n"
            "<!-- Written by gattuccino, and rewritten whenever the flavor or the accent changes. Edits are\n"
            "     overwritten. The colors are the ones of the official port, https://github.com/catppuccin/gnome-text-editor,\n"
            "     with the accent for the cursor and the number of the current line. -->\n")
    return f"{declaration}\n{note}{rest}"


class GnomeTextEditor(Tool):
    name = "gnome_text_editor"
    label = "GNOME Text Editor"
    command = "gnome-text-editor"
    help = ("Theme GNOME Text Editor with Catppuccin, light and dark; it follows the flavor and the accent "
            "(its cursor and current line number)")

    def folder(self, desktop) -> str:
        return f"{desktop.data_dir}/gtksourceview-5/styles"

    def paths(self, desktop) -> dict:
        return {LIGHT_ID: f"{self.folder(desktop)}/{LIGHT_ID}.xml", DARK_ID: f"{self.folder(desktop)}/{DARK_ID}.xml"}

    def sync(self, context):
        desktop = context.desktop
        paths = self.paths(desktop)
        write_managed(paths[LIGHT_ID], scheme_text("latte", context.accent, dark=False), context.notes)
        write_managed(paths[DARK_ID], scheme_text(context.dark_flavor, context.accent, dark=True), context.notes)

        current = desktop.gsettings_get(SCHEMA, "style-scheme")
        if current is not None and current not in (LIGHT_ID, DARK_ID):
            context.state["previous"] = current
            desktop.gsettings_set(SCHEMA, "style-scheme", LIGHT_ID)
        variant = desktop.gsettings_get(SCHEMA, "style-variant")
        if variant in ("light", "dark"):
            context.notes.append(
                f"GNOME Text Editor is set to stay {variant} (style-variant), whatever the style of the desktop "
                "is: set it to follow in its preferences for it to change between Latte and your dark flavor.")

    def remove(self, context):
        desktop, state = context.desktop, context.state
        for path in self.paths(desktop).values():
            remove_managed(path)
        if "previous" in state and desktop.gsettings_get(SCHEMA, "style-scheme") in (LIGHT_ID, DARK_ID):
            desktop.gsettings_set(SCHEMA, "style-scheme", state["previous"])
        state.clear()
