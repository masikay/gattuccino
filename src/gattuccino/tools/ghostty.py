"""Ghostty, the terminal, which reads `config.ghostty` in its configuration folder
(`$XDG_CONFIG_HOME/ghostty`, or `~/.config/ghostty`), and themes from the folder
`themes` next to it.

The themes are the ones of the official Catppuccin port, one for each flavor,
unchanged (see data/tools/ghostty/SOURCE.md). The port has no accent: the
`cursor-color`, where it has rosewater, is given the accent in use.

Both styles are written at once, the one of Latte as `themes/gattuccino-light` and
the one of the dark flavor as `themes/gattuccino-dark`, and `theme = light:...,dark:...`
in a file of this project's, `gattuccino`, next to the configuration. Ghostty
follows the style of the desktop by itself, so it changes between the two as it is
switched, with no help; a change of flavor or of accent is a change of the files,
which a Ghostty that is running reads again when it is asked to.

The configuration of a person is touched in one place, by one line:
`config-file = ?gattuccino`, which Ghostty reads after everything else in the file, so
that its `theme` is the one that counts, whatever the file has. A `config.ghostty` that
is a symlink, into a dotfiles repository say, is never written through: a note says what
to put in the file it points to.
"""

import os
import re

from .. import palette
from . import DATA, MARKER, Tool, header, is_ours, remove_managed, write_managed

THEMES = os.path.join(DATA, "ghostty", "themes")
INCLUDE = "gattuccino"                                    # the file this project's, next to the configuration
LINE = "config-file = ?gattuccino"
COMMENT = f"{MARKER} the theme of gattuccino, in the file of this name next to this one"
CURSOR = re.compile(r"^cursor-color = [0-9A-Fa-f]{6}$", re.MULTILINE)
BUS_NAME = "com.mitchellh.ghostty"
BUS_PATH = "/com/mitchellh/ghostty"


def theme_file(flavor: str) -> str:
    return os.path.join(THEMES, f"catppuccin-{flavor}.conf")


def with_accent(theme: str, color: str) -> str:
    """The official theme, with the accent for the cursor."""
    return CURSOR.sub(f"cursor-color = {color.lstrip('#').lower()}", theme)


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _write(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Ghostty(Tool):
    name = "ghostty"
    label = "Ghostty"
    command = "ghostty"
    help = "Theme Ghostty, the terminal, with Catppuccin, light and dark; it follows the flavor and the accent"

    def folder(self, desktop) -> str:
        return f"{desktop.config_dir}/ghostty"

    def config_path(self, desktop) -> str:
        """The configuration file there is, or the one Ghostty reads first when there is none."""
        folder = self.folder(desktop)
        for name in ("config.ghostty", "config"):
            if os.path.lexists(f"{folder}/{name}"):
                return f"{folder}/{name}"
        return f"{folder}/config.ghostty"

    def themes(self, desktop) -> dict:
        folder = self.folder(desktop)
        return {"light": f"{folder}/themes/gattuccino-light", "dark": f"{folder}/themes/gattuccino-dark"}

    def sync(self, context):
        desktop = context.desktop
        folder = self.folder(desktop)
        before = [_read(path) for path in (*self.themes(desktop).values(), f"{folder}/{INCLUDE}")]

        for style, flavor in (("light", "latte"), ("dark", context.dark_flavor)):
            color = palette.color(flavor, context.accent)
            text = header(f"ghostty theme, {style}", flavor, context.accent,
                          "# The colors are the ones of the official port, https://github.com/catppuccin/ghostty,\n"
                          "# with the accent for the cursor.\n\n") + with_accent(_read(theme_file(flavor)), color)
            write_managed(self.themes(desktop)[style], text, context.notes)
        write_managed(f"{folder}/{INCLUDE}",
                      header("ghostty theme", f"latte and {context.dark_flavor}", context.accent)
                      + "theme = light:gattuccino-light,dark:gattuccino-dark\n", context.notes)
        self.include_it(context)

        after = [_read(path) for path in (*self.themes(desktop).values(), f"{folder}/{INCLUDE}")]
        if before != after:
            self.reload(desktop)

    def include_it(self, context):
        """Put `config-file = ?gattuccino` in the configuration, once."""
        desktop, state = context.desktop, context.state
        path = self.config_path(desktop)
        if os.path.islink(path):
            context.notes.append(
                f"{path} is a symlink, so it is not edited: put `{LINE}` in the file it points to, "
                "and Ghostty has the theme.")
            return
        if not os.path.exists(path):
            _write(path, f"{COMMENT}\n{LINE}\n")
            state.clear()
            state["created"] = True
            return
        text = _read(path)
        if re.search(rf"^{re.escape(LINE)}\s*$", text, re.MULTILINE):
            return   # there already
        state.clear()
        state["added"] = True
        if re.search(r"^theme\s*=", text, re.MULTILINE):
            context.notes.append("Your own `theme` in the configuration of Ghostty stays, and is overridden by "
                                 "the one of gattuccino, which is read after it, for as long as the tool is on.")
        _write(path, text + ("" if text.endswith("\n") or not text else "\n") + f"{COMMENT}\n{LINE}\n")

    def reload(self, desktop):
        """Ask a Ghostty that is running to read its configuration again. Only one that is: the service
        is started by anything that asks it for an action, and a window is not wanted."""
        if not desktop.has("gdbus"):
            return
        running = desktop.run("gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                              "--object-path", "/org/freedesktop/DBus", "--method",
                              "org.freedesktop.DBus.NameHasOwner", BUS_NAME)
        if running.returncode == 0 and "true" in running.stdout:
            desktop.run("gdbus", "call", "--session", "--dest", BUS_NAME, "--object-path", BUS_PATH,
                        "--method", "org.gtk.Actions.Activate", "reload-config", "[]", "{}")

    def remove(self, context):
        desktop, state = context.desktop, context.state
        folder = self.folder(desktop)
        changed = any(is_ours(path) for path in (*self.themes(desktop).values(), f"{folder}/{INCLUDE}"))
        for path in (*self.themes(desktop).values(), f"{folder}/{INCLUDE}"):
            remove_managed(path)

        path = self.config_path(desktop)
        if not os.path.islink(path) and os.path.exists(path):
            text = _read(path)
            lines = [line for line in text.split("\n") if line.strip() not in (LINE, COMMENT)]
            if lines != text.split("\n"):
                changed = True
                rest = "\n".join(lines)
                if state.get("created") and not rest.strip():
                    os.remove(path)   # the one line this project made the file of
                else:
                    _write(path, rest)
        state.clear()
        if changed:
            self.reload(desktop)
