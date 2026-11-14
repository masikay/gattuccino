"""eza, the replacement for ls, which reads its colors from `theme.yml` in its
configuration folder (`$EZA_CONFIG_DIR`, or `~/.config/eza`).

The themes are the ones of the official Catppuccin port, one for each flavor and
accent, unchanged (see data/tools/eza/SOURCE.md); the one in use is copied in
under a first line of this project's.
"""

import os

from . import DATA, Tool, header, remove_managed, write_managed

THEMES = os.path.join(DATA, "eza", "themes")

# What LS_COLORS can say that eza then does instead of its theme, by the key it is said with
KINDS = {"di": "folders", "ln": "symlinks", "ex": "executables", "pi": "pipes", "so": "sockets",
         "bd": "block devices", "cd": "character devices"}


def theme_file(flavor: str, accent: str) -> str:
    return os.path.join(THEMES, flavor, f"catppuccin-{flavor}-{accent}.yml")


class Eza(Tool):
    name = "eza"
    label = "eza"
    command = "eza"
    help = "Theme eza, the ls replacement, with Catppuccin in its theme.yml; it follows the flavor and the accent"

    def path(self, desktop) -> str:
        folder = desktop.environment.get("EZA_CONFIG_DIR") or f"{desktop.config_dir}/eza"
        return f"{folder}/theme.yml"

    def sync(self, context):
        with open(theme_file(context.flavor, context.accent), "r", encoding="utf-8") as f:
            theme = f.read()
        text = header("eza theme", context.flavor, context.accent,
                      "# The theme is the one of the official port, https://github.com/catppuccin/eza\n\n") + theme
        write_managed(self.path(context.desktop), text, context.notes)
        self.warn_about_ls_colors(context)

    def warn_about_ls_colors(self, context):
        """eza gives LS_COLORS priority over its theme, kind by kind: where it says anything about
        folders, symlinks and the like, the theme is not what is shown (the accent is the color of
        folders). Fedora, for one, sets it in every shell."""
        keys = {entry.split("=", 1)[0] for entry in context.desktop.environment.get("LS_COLORS", "").split(":")}
        overridden = [what for key, what in KINDS.items() if key in keys]
        if overridden:
            context.notes.append(
                f"LS_COLORS is set in your shell, and eza gives it priority over its theme for "
                f"{', '.join(overridden)}: they keep the colors it says, whatever the flavor and the accent. "
                "Clear it for eza, with `LS_COLORS= eza` in your aliases, or with `unset LS_COLORS` in your shell's "
                "configuration. See the README.")

    def remove(self, context):
        remove_managed(self.path(context.desktop))
