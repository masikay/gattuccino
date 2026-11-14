"""Catppuccin for the tools in a terminal, kept in step with the flavor and the
accent of the theme.

Each tool is a small adapter (a module here) that knows where the tool keeps its
theme and how to put the Catppuccin one there. A person chooses the tools they
want in `configure`, one preference each (`tool_NAME`, off by default), and
`sync` writes the theme of the flavor and accent in use for those, and takes
what it wrote away for the others. It is run by `apply`, by `configure`, and by
the catppuccin-accent extension whenever the style or the accent is changed in
Settings.

What an adapter writes is marked as this project's, and what was there before is
kept beside it and put back when the tool is turned off: a person's own theme
is never lost, and never written through (a symlink into a dotfiles repository
is moved aside as it is, and not written into).
"""

import os
import time
from dataclasses import dataclass, field


PREFIX = "tool_"
MARKER = "# gattuccino:"
BACKUP_SUFFIX = ".before-gattuccino"
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data", "tools")


@dataclass
class Context:
    """What an adapter is given: the machine, and the flavor and accent in use."""
    desktop: object
    flavor: str
    accent: str
    notes: list = field(default_factory=list)


class Tool:
    name = ""      # the preference is tool_NAME
    label = ""     # as a person calls it
    command = ""   # what is run, to tell it is installed
    help = ""      # what is done, for the preference

    def installed(self, desktop) -> bool:
        return desktop.has(self.command or self.name)

    def sync(self, context: Context):
        raise NotImplementedError

    def remove(self, context: Context):
        raise NotImplementedError

    @property
    def preference(self) -> str:
        return PREFIX + self.name


# --- Files that are this project's ---------------------------------------------

def is_ours(path: str) -> bool:
    """Whether a file was written by this project: its first line says so. A symlink never is."""
    if os.path.islink(path) or not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.readline().startswith(MARKER)
    except OSError:
        return False


def header(what: str, flavor: str, accent: str, extra: str = "") -> str:
    return (f"{MARKER} {what} (flavor={flavor}, accent={accent})\n"
            f"# Written by gattuccino, and rewritten whenever the flavor or the accent changes.\n"
            f"# Edits are overwritten. Turn it off in `gattuccino configure` or in its window.\n{extra}")


def write_managed(path: str, text: str, notes: list):
    """Write a file of this project's, keeping what was there before beside it.

    What is there that is not ours (a file of the person's own, or a symlink to
    one) is moved to `NAME.before-gattuccino` as it is, once, and is put back by
    `remove_managed`. A symlink is moved as a link: it is never written through.
    """
    if os.path.lexists(path) and not is_ours(path):
        backup = path + BACKUP_SUFFIX
        if os.path.lexists(backup):   # never overwrite an earlier backup
            backup += time.strftime(".%Y%m%d-%H%M%S")
        os.replace(path, backup)
        notes.append(f"Your own {path} was kept as {os.path.basename(backup)}.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.islink(path):   # one of ours that was replaced by a link since
        os.remove(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def remove_managed(path: str):
    """Take a file of this project's away, and put back the one it replaced."""
    if is_ours(path):
        os.remove(path)
    if os.path.lexists(path):
        return   # something of the person's own is there: it stays
    backup = path + BACKUP_SUFFIX
    if os.path.lexists(backup):
        os.replace(backup, path)


# --- The registry --------------------------------------------------------------

def all_tools() -> list:
    from . import eza
    return [eza.Eza()]


def by_preference(name: str):
    return next((tool for tool in all_tools() if tool.preference == name), None)


def preference_names() -> list:
    return [tool.preference for tool in all_tools()]


def installed(name: str, desktop) -> bool:
    """Whether the tool of a preference is on the machine; True for anything that is not one."""
    tool = by_preference(name)
    return True if tool is None else tool.installed(desktop)


def sync(desktop, preferences, flavor: str, accent: str, notes: list, log=lambda _line: None) -> list:
    """Write the theme of each tool that is wanted, and take away the others'. Returns the names written."""
    context = Context(desktop, flavor, accent, notes)
    written = []
    for tool in all_tools():
        if getattr(preferences, tool.preference):
            if not tool.installed(desktop):
                notes.append(f"{tool.label} is not installed, so it is not themed.")
                tool.remove(context)
                continue
            tool.sync(context)
            written.append(tool.name)
            log(f"Themed {tool.label} ({flavor}, {accent})")
        else:
            tool.remove(context)
    return written


def remove_all(desktop):
    context = Context(desktop, "", "")
    for tool in all_tools():
        tool.remove(context)


def wanted(preferences) -> bool:
    """Whether any tool is wanted, which is when the extension has something to run."""
    return any(getattr(preferences, tool.preference) for tool in all_tools())

