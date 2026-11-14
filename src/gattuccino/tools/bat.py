"""bat, the replacement for cat with syntax highlighting, which finds a theme by the
name of its file among the `.tmTheme` files of `themes` in its configuration folder
(`$XDG_CONFIG_HOME/bat`, or `~/.config/bat`), once `bat cache --build` has put it in its
cache, and which is told what theme to use by `--theme` in its configuration file or by
`BAT_THEME` in the environment, which wins.

The themes are the ones of the official Catppuccin port, one for each flavor, unchanged
(see data/tools/bat/SOURCE.md). The port has no accent, and a theme of bat has no place
for one. The one in use is written to `themes/gattuccino.tmTheme`, the cache is built
again, and `BAT_THEME=gattuccino` is put in a file of environment.d, which the session
reads at login: so bat has it in every shell, and the configuration file of a person,
which may be a symlink into a dotfiles repository, is not touched.

Shells that were started with `BAT_THEME=gattuccino` keep it until the next login, and bat
warns about a theme it does not know: so when the tool is turned off the theme is left
where it is until the variable is gone.
"""

import os

from . import (DATA, Tool, header, is_ours, remove_environment, remove_managed, same_content,
               write_environment, write_managed)

THEMES = os.path.join(DATA, "bat", "themes")
NAME = "gattuccino"
FLAVOR_NAMES = {"latte": "Latte", "frappe": "Frappe", "macchiato": "Macchiato", "mocha": "Mocha"}


def theme_file(flavor: str) -> str:
    return os.path.join(THEMES, f"Catppuccin {FLAVOR_NAMES[flavor]}.tmTheme")


def theme_text(flavor: str, accent: str) -> str:
    """The official theme, under the declaration of the XML and a line that says whose file it is."""
    with open(theme_file(flavor), "r", encoding="utf-8") as f:
        text = f.read()
    declaration, _, rest = text.partition("\n")
    marker = f"<!-- gattuccino: bat theme (flavor={flavor}, accent={accent}) -->\n"
    note = ("<!-- Written by gattuccino, and rewritten whenever the flavor changes. Edits are overwritten.\n"
            "     The colors are the ones of the official port, https://github.com/catppuccin/bat. -->\n")
    return f"{declaration}\n{marker}{note}{rest}"


class Bat(Tool):
    name = "bat"
    label = "bat"
    command = "bat"
    help = "Theme bat, the cat with syntax highlighting, with Catppuccin; it follows the flavor"

    def theme_path(self, desktop) -> str:
        return f"{desktop.config_dir}/bat/themes/{NAME}.tmTheme"

    def sync(self, context):
        desktop = context.desktop
        path = self.theme_path(desktop)
        text = theme_text(context.flavor, context.accent)
        if not same_content(path, text):
            write_managed(path, text, context.notes)
            self.build_cache(desktop)
        write_environment(context, "bat", header("bat theme", context.flavor, context.accent)
                          + f"BAT_THEME={NAME}\n")
        self.warn(context)

    def build_cache(self, desktop):
        """bat knows a theme once its cache has been built again."""
        desktop.run("bat", "cache", "--build")

    def warn(self, context):
        environment = context.desktop.environment
        if environment.get("BAT_THEME") != NAME:
            if environment.get("BAT_THEME"):
                context.notes.append(
                    f"BAT_THEME is {environment['BAT_THEME']!r} in your shell, and wins over the theme of "
                    "gattuccino: take it out of your shell configuration to let this one show.")
            else:
                context.notes.append(
                    "BAT_THEME is set at login: log out and back in, and bat in every new shell has the theme "
                    "(after that, a new bat has the new flavor as soon as it changes). If it is still empty "
                    "after that, the session was started again within ten seconds of logging out, and systemd "
                    "kept its old environment: log out, wait a little, or restart.")

    def remove(self, context):
        desktop = context.desktop
        path = self.theme_path(desktop)
        remove_environment(context, "bat")
        if not is_ours(path):
            return
        if desktop.environment.get("BAT_THEME") == NAME:
            return   # shells that have the variable go on with the theme, until the next login
        remove_managed(path)
        self.build_cache(desktop)
