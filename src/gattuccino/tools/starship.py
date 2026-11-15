"""Starship, the prompt, which reads one configuration file (`$STARSHIP_CONFIG`, or
`~/.config/starship.toml`) on every prompt, and colors by the names of a palette: `palette =
'NAME'` at the top, and a table `[palettes.NAME]` of colors, which the styles of the file use
(`fg:mauve`, `bg:lavender`).

The file Starship reads is written: the same configuration, with `palette` set to the
`gattuccino` palette, which is added: the colors of the flavor in use, under the names of the
official Catppuccin palette, and `accent`, the accent in use, for a style that wants it
(`fg:accent`). So nothing in the shell has to change.

What it is made of is the configuration that was there. A person's file is often a symlink
into a dotfiles repository, which is never written through: the link is moved aside, as
`starship.toml.before-gattuccino`, and the file it led to is the one the new one is made of
(that is remembered, as the sync that the extension runs has no shell, and so no
`STARSHIP_CONFIG`; the same goes for the path the file is written to). A file of the person's
own that is not a link is moved aside the same way. Both are put back when the tool is turned
off. The file is made again whenever the flavor or the accent changes, and at each login,
which is when edits to the original reach it: edit the original, not this file.
"""

import os
import re

from .. import palette
from . import BACKUP_SUFFIX, Tool, header, is_ours, remove_managed, same_content, write_managed

NAME = "gattuccino"
TABLE = re.compile(r"^\s*\[")
PALETTE_LINE = re.compile(r"^palette\s*=.*$")


def palette_table(flavor: str, accent: str) -> str:
    colors = dict(palette.FLAVORS[flavor])
    colors["accent"] = palette.color(flavor, accent).lower()
    return f"[palettes.{NAME}]\n" + "".join(f'{name} = "{value}"\n' for name, value in colors.items())


def first_table(lines: list) -> int:
    """The index of the first table, `[name]`, which is not a line of a multi-line string."""
    quote = None
    for i, line in enumerate(lines):
        if quote is None and TABLE.match(line):
            return i
        for mark in ('"""', "\'\'\'"):
            if line.count(mark) % 2:
                quote = None if quote == mark else (quote or mark)
    return len(lines)


def make(source: str, flavor: str, accent: str, original: str) -> str:
    """The configuration, as the copy of it that has the palette of gattuccino."""
    lines = source.split("\n")
    split = first_table(lines)
    top, rest = lines[:split], lines[split:]
    if any(PALETTE_LINE.match(line) for line in top):
        top = [f"palette = '{NAME}'" if PALETTE_LINE.match(line) else line for line in top]
    else:
        top.insert(0, f"palette = '{NAME}'")
    text = "\n".join(top + rest).rstrip("\n") + "\n\n"
    # a table of this name that was in the file is replaced by this one
    text = re.sub(rf"(?ms)^\[palettes\.{NAME}\]\n.*?(?=^\[|\Z)", "", text).rstrip("\n") + "\n\n"
    return (header("starship configuration", flavor, accent,
                   f"# A copy of {original}, with the palette '{NAME}' (the colors of the flavor, and `accent`).\n\n")
            + text + palette_table(flavor, accent))


class Starship(Tool):
    name = "starship"
    label = "Starship"
    command = "starship"
    help = ("Theme Starship, the prompt, with Catppuccin: its configuration is written again with the "
            "palette of the flavor and the accent in use")

    def path(self, context) -> str:
        """The file Starship reads: what STARSHIP_CONFIG names, or what was found so, or the default."""
        desktop, state = context.desktop, context.state
        named = desktop.environment.get("STARSHIP_CONFIG")
        if named:
            state["target"] = named
        return state.get("target") or f"{desktop.config_dir}/starship.toml"

    def source(self, context, path):
        """The configuration to make the new one of, and where it is; remembered."""
        state = context.state
        backup = path + BACKUP_SUFFIX
        if os.path.lexists(path) and not is_ours(path):
            state["source"] = os.path.realpath(path)        # a link leads on; a file is itself, until moved
        elif os.path.islink(backup) and "source" not in state:
            state["source"] = os.path.realpath(backup)
        source = state.get("source")
        return source if source and os.path.isfile(source) else None

    def sync(self, context):
        path = self.path(context)
        source = self.source(context, path)
        if source is None:
            context.notes.append(
                f"Starship has no configuration to make the theme of: {path} is not there. Put yours in it "
                "(or leave a link to it there) and run `gattuccino configure` again.")
            return
        try:
            with open(source, "r", encoding="utf-8") as f:
                original = f.read()
        except OSError as e:
            context.notes.append(f"{source} could not be read ({e.strerror}), so Starship is left as it was.")
            return
        text = make(original, context.flavor, context.accent, source)
        if same_content(path, text):
            return
        was_ours = is_ours(path)
        write_managed(path, text, context.notes)
        if not was_ours and os.path.isfile(path + BACKUP_SUFFIX) and not os.path.islink(path + BACKUP_SUFFIX):
            context.state["source"] = path + BACKUP_SUFFIX   # a file that was moved aside is where it is now

    def remove(self, context):
        remove_managed(self.path(context))
        context.state.clear()
