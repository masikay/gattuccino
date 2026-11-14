"""fzf, the fuzzy finder, which reads its default options from a file when
`FZF_DEFAULT_OPTS_FILE` names one (fzf 0.58 and later).

The colors are the ones of the official Catppuccin port, one file for each
flavor, unchanged (see data/tools/fzf/SOURCE.md). The port has no accent: the
`prompt` and the `pointer` are given the accent in use, where the port has mauve
and rosewater. The file is written to `~/.config/fzf/gattuccino.rc`, and
`FZF_DEFAULT_OPTS_FILE` is pointed at it through `environment.d`, which the
session reads at login, so that every shell has it without a line in its
configuration. The user manager of systemd, which reads it, is kept running
when a person logs back in within ten seconds of logging out, and then never
sees the file: so it is asked to read it again, and the next login has the
variable whatever happened before.

Two things can keep the colors from showing, and are said: an fzf older than
0.58, and a `FZF_DEFAULT_OPTS` of the shell with `--color` in it, which is read
after the file and wins.
"""

import os
import re

from .. import palette
from . import DATA, Tool, header, is_ours, remove_managed, write_managed

THEMES = os.path.join(DATA, "fzf", "themes")
VARIABLE = "FZF_DEFAULT_OPTS_FILE"
FIRST_VERSION = (0, 58)
ACCENT_KEYS = re.compile(r"\b(pointer|prompt):#[0-9A-Fa-f]{6}")


def same_content(path: str, text: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read() == text
    except OSError:
        return False


def theme_file(flavor: str) -> str:
    return os.path.join(THEMES, f"catppuccin-fzf-{flavor}.rc")


def with_accent(theme: str, color: str) -> str:
    """The official theme, with the accent for the `pointer` and the `prompt`."""
    return ACCENT_KEYS.sub(lambda m: f"{m.group(1)}:{color.upper()}", theme)


class Fzf(Tool):
    name = "fzf"
    label = "fzf"
    command = "fzf"
    help = "Theme fzf, the fuzzy finder, with Catppuccin; it follows the flavor and the accent (its prompt and pointer)"

    def options_path(self, desktop) -> str:
        return f"{desktop.config_dir}/fzf/gattuccino.rc"

    def environment_path(self, desktop) -> str:
        return f"{desktop.config_dir}/environment.d/60-gattuccino-fzf.conf"

    def version(self, desktop):
        result = desktop.run("fzf", "--version")
        match = re.match(r"(\d+)\.(\d+)", result.stdout.strip()) if result.returncode == 0 else None
        return (int(match.group(1)), int(match.group(2))) if match else None

    def sync(self, context):
        desktop = context.desktop
        with open(theme_file(context.flavor), "r", encoding="utf-8") as f:
            theme = f.read()
        color = palette.color(context.flavor, context.accent)
        options = header("fzf theme", context.flavor, context.accent,
                         "# The colors are the ones of the official port, https://github.com/catppuccin/fzf,\n"
                         "# with the accent for the prompt and the pointer.\n\n") + with_accent(theme, color)
        path = self.options_path(desktop)
        write_managed(path, options, context.notes)

        environment = self.environment_path(desktop)
        text = header("fzf options file", context.flavor, context.accent) + f"{VARIABLE}={path}\n"
        if not same_content(environment, text):
            write_managed(environment, text, context.notes)
            desktop.run("systemctl", "--user", "daemon-reload")   # a user manager that is still running reads it again
        self.warn(context, path)

    def warn(self, context, path):
        desktop = context.desktop
        version = self.version(desktop)
        if version is not None and version < FIRST_VERSION:
            context.notes.append(
                f"fzf {version[0]}.{version[1]} is older than 0.58, which is the first to read {VARIABLE}: "
                "its colors will not show until it is updated.")
        if desktop.environment.get(VARIABLE) != path:
            context.notes.append(
                f"{VARIABLE} is set at login: log out and back in, and fzf in every new shell has the theme "
                "(after that, a new fzf has the new flavor and accent as soon as they change). If it is still "
                "empty after that, the session was started again within ten seconds of logging out, and systemd "
                "kept its old environment: log out, wait a little, or restart.")
        if "--color" in desktop.environment.get("FZF_DEFAULT_OPTS", ""):
            context.notes.append(
                "FZF_DEFAULT_OPTS in your shell has --color in it, and is read after the theme: its colors win. "
                "Take the colors out of it, or its line sourcing a Catppuccin theme, to let this one show.")

    def remove(self, context):
        remove_managed(self.options_path(context.desktop))
        environment = self.environment_path(context.desktop)
        if is_ours(environment):
            remove_managed(environment)
            context.desktop.run("systemctl", "--user", "daemon-reload")
