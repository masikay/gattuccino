"""lazygit, the terminal interface of git, which reads its configuration from
`config.yml` in its configuration folder (`$XDG_CONFIG_HOME/lazygit`, or
`~/.config/lazygit`), and from every file that `LG_CONFIG_FILE` lists, separated by commas,
each over the ones before it.

The theme is the one of the official Catppuccin port, which has the flavor and the accent
in the name of its files, unchanged (see data/tools/lazygit/SOURCE.md): the one in use is
written to `gattuccino.yml` next to the configuration, and `LG_CONFIG_FILE` is set, through
`environment.d`, which the session reads at login, to the configuration and that file. So
every shell has it, and the configuration of a person, which may be a symlink into a
dotfiles repository, is not touched. The user manager of systemd is asked to read the file
again, as it is kept running when a person logs back in within ten seconds of logging out.

lazygit stops when a file that `LG_CONFIG_FILE` lists is not there: so `config.yml` is made,
empty, as lazygit would at its first run, when it is missing, and when the tool is turned off
the theme is left, empty, where it is until the variable is gone.
"""

import os

from . import (DATA, MARKER, Tool, header, is_ours, remove_environment, remove_managed, same_content,
               write_environment, write_managed)

THEMES = os.path.join(DATA, "lazygit", "themes")
VARIABLE = "LG_CONFIG_FILE"


def theme_file(flavor: str, accent: str) -> str:
    return os.path.join(THEMES, flavor, f"{accent}.yml")


class Lazygit(Tool):
    name = "lazygit"
    label = "lazygit"
    command = "lazygit"
    help = "Theme lazygit, the terminal interface of git, with Catppuccin; it follows the flavor and the accent"

    def folder(self, desktop) -> str:
        return f"{desktop.config_dir}/lazygit"

    def theme_path(self, desktop) -> str:
        return f"{self.folder(desktop)}/gattuccino.yml"

    def config_path(self, desktop) -> str:
        return f"{self.folder(desktop)}/config.yml"

    def files(self, desktop) -> str:
        return f"{self.config_path(desktop)},{self.theme_path(desktop)}"

    def sync(self, context):
        desktop = context.desktop
        with open(theme_file(context.flavor, context.accent), "r", encoding="utf-8") as f:
            theme = f.read()
        text = header("lazygit theme", context.flavor, context.accent,
                      "# The colors are the ones of the official port, https://github.com/catppuccin/lazygit.\n\n") + theme
        write_managed(self.theme_path(desktop), text, context.notes)

        config = self.config_path(desktop)
        if not os.path.lexists(config):
            os.makedirs(os.path.dirname(config), exist_ok=True)
            open(config, "a").close()
            context.notes.append(f"{config} was not there, and lazygit does not start when a file it is "
                                 "told of is missing: it was made empty, as lazygit would.")
        write_environment(context, "lazygit", header("lazygit configuration files", context.flavor, context.accent)
                          + f"{VARIABLE}={self.files(desktop)}\n")
        self.warn(context)

    def warn(self, context):
        environment = context.desktop.environment
        named = environment.get(VARIABLE)
        if named == self.files(context.desktop):
            return
        if named:
            context.notes.append(
                f"{VARIABLE} is {named!r} in your shell, and the theme of gattuccino is not in it: take the "
                "line that sets it out of your shell configuration, or add the file "
                f"{self.theme_path(context.desktop)} to the list, last.")
        else:
            context.notes.append(
                f"{VARIABLE} is set at login: log out and back in, and lazygit in every new shell has the theme "
                "(after that, a new lazygit has the new flavor and accent as soon as they change). If it is "
                "still empty after that, the session was started again within ten seconds of logging out, and "
                "systemd kept its old environment: log out, wait a little, or restart.")

    def remove(self, context):
        desktop = context.desktop
        path = self.theme_path(desktop)
        remove_environment(context, "lazygit")
        if desktop.environment.get(VARIABLE) == self.files(desktop) and is_ours(path):
            # Shells that were started with the variable go on having it until the next login, and lazygit
            # does not start with a file that is not there: it is left empty, and goes later
            stub = f"{MARKER} lazygit theme (off)\n# Nothing: the tool is off. This file goes at the next login.\n"
            if not same_content(path, stub):
                write_managed(path, stub, context.notes)
        else:
            remove_managed(path)
