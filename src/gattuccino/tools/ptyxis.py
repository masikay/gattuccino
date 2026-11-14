"""Ptyxis, the terminal of GNOME, which keeps its color palette in the settings of each
of its profiles (`org.gnome.Ptyxis.Profile`, key `palette`, a name), and finds the
palettes by name among the `.palette` files of `~/.local/share/org.gnome.Ptyxis/palettes`
and the ones it brings along.

There is no official Catppuccin port for Ptyxis (its own Catppuccin palettes were made from
the ones of Gogh), so the palette is made from the official port for Ghostty, which has the
colors the Catppuccin terminals share: the sixteen colors, the background and the foreground,
and the cursor (see data/tools/ghostty/SOURCE.md). The cursor takes the accent in use.

Both styles are in one palette, `Gattuccino`: Latte as its `[Light]` and the dark flavor as
its `[Dark]`, and Ptyxis chooses between them by itself, as the style of the desktop is
switched. The profiles are pointed at it, and what they had is remembered (in the state
file) to be put back. Ptyxis reads its palettes when it starts, so a change of flavor or of
accent is seen only after the Ptyxis service has quit (it stays running, as
`ptyxis --gapplication-service`, when its last window is closed) and is started again.

A Ptyxis whose `interface-style` is not `system` is kept in one style, light or dark, whatever
the desktop does, and is said to be.
"""

import os
import re

from .. import palette
from . import Tool, header, remove_managed, write_managed
from .ghostty import theme_file

NAME = "Gattuccino"
PROFILE = "org.gnome.Ptyxis.Profile:/org/gnome/Ptyxis/Profiles/{}/"
GHOSTTY_LINE = re.compile(r"^([a-z-]+) = (?:(\d+)=)?#?([0-9a-fA-F]{6})$", re.MULTILINE)


def colors(flavor: str) -> dict:
    """What the official Ghostty theme of a flavor says: 'color0' to 'color15', 'background',
    'foreground', 'cursor-color', 'cursor-text'."""
    with open(theme_file(flavor), "r", encoding="utf-8") as f:
        text = f.read()
    result = {}
    for key, number, value in GHOSTTY_LINE.findall(text):
        result[f"color{number}" if key == "palette" else key] = "#" + value.lower()
    return result


def scheme(flavor: str, accent: str) -> str:
    """One section of the palette, `[Light]` or `[Dark]` without its title."""
    theirs = colors(flavor)
    lines = [f"Foreground={theirs['foreground']}", f"Background={theirs['background']}",
             f"Cursor={palette.color(flavor, accent).lower()}", f"CursorForeground={theirs['cursor-text']}"]
    lines += [f"Color{n}={theirs[f'color{n}']}" for n in range(16)]
    return "\n".join(lines) + "\n"


class Ptyxis(Tool):
    name = "ptyxis"
    label = "Ptyxis"
    command = "ptyxis"
    help = "Theme Ptyxis, the terminal of GNOME, with Catppuccin, light and dark; it follows the flavor and the accent (its cursor)"

    def path(self, desktop) -> str:
        return f"{desktop.data_dir}/org.gnome.Ptyxis/palettes/{NAME}.palette"

    def sync(self, context):
        desktop = context.desktop
        text = (header("ptyxis palette", f"latte and {context.dark_flavor}", context.accent,
                       "# The colors are the ones of the official Catppuccin port for Ghostty,\n"
                       "# https://github.com/catppuccin/ghostty, with the accent for the cursor.\n\n")
                + f"[Palette]\nName={NAME}\n\n[Light]\n{scheme('latte', context.accent)}\n"
                + f"[Dark]\n{scheme(context.dark_flavor, context.accent)}")
        write_managed(self.path(desktop), text, context.notes)
        self.use_it(context)

    def profiles(self, desktop) -> list:
        uuids = desktop.gsettings_get("org.gnome.Ptyxis", "profile-uuids")
        return [u for u in uuids if isinstance(u, str)] if isinstance(uuids, list) else []

    def use_it(self, context):
        """Point the profiles at the palette, remembering what each one had."""
        desktop, state = context.desktop, context.state
        previous = state.setdefault("previous", {})
        for uuid in self.profiles(desktop):
            schema = PROFILE.format(uuid)
            current = desktop.gsettings_get(schema, "palette")
            if current is None or current == NAME:
                continue
            previous[uuid] = current
            desktop.gsettings_set(schema, "palette", NAME)

        style = desktop.gsettings_get("org.gnome.Ptyxis", "interface-style")
        if style in ("light", "dark"):
            context.notes.append(
                f"Ptyxis is set to stay {style} (interface-style), whatever the style of the desktop is: "
                "set it to `system` in its preferences, or `gsettings set org.gnome.Ptyxis interface-style "
                "system`, for it to follow the desktop between Latte and your dark flavor.")

    def remove(self, context):
        desktop, state = context.desktop, context.state
        remove_managed(self.path(desktop))
        for uuid, before in state.get("previous", {}).items():
            schema = PROFILE.format(uuid)
            if desktop.gsettings_get(schema, "palette") == NAME:
                desktop.gsettings_set(schema, "palette", before)
        state.clear()
