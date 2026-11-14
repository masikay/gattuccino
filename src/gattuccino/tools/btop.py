"""btop, the resource monitor, which reads a theme by name from `btop.conf` and
looks for it among the files of `themes` in its configuration folder
(`$XDG_CONFIG_HOME/btop`, or `~/.config/btop`).

The themes are the ones of the official Catppuccin port, one for each flavor,
unchanged (see data/tools/btop/SOURCE.md). The port has no accent: `hi_fg` and
`selected_fg`, where it has blue, are given the accent in use. The one in use is
written to `themes/gattuccino.theme`, and `btop.conf` is made to ask for it by
that name.

`btop.conf` is the one file here that is not this project's: it is btop's, who
writes it back whenever a setting is changed in it, and holds all of a person's
settings. So only its `color_theme` line is touched, and what was there is
remembered (in the state file) to be put back; a `btop.conf` that is a symlink,
into a dotfiles repository say, is never written through, and is left for the
person to point at the theme.
"""

import os
import re
import tempfile

from .. import palette
from . import DATA, Tool, header, remove_managed, write_managed

THEMES = os.path.join(DATA, "btop", "themes")
NAME = "gattuccino"                  # the name btop asks for: themes/gattuccino.theme
LINE = re.compile(r'^color_theme[ \t]*=[ \t]*"?([^"\n]*?)"?[ \t]*$', re.MULTILINE)
ACCENT_KEYS = re.compile(r'(theme\[(?:hi_fg|selected_fg)\]=)"#[0-9A-Fa-f]{6}"')


def theme_file(flavor: str) -> str:
    return os.path.join(THEMES, f"catppuccin_{flavor}.theme")


def with_accent(theme: str, color: str) -> str:
    """The official theme, with the accent for the highlighted keys and the selected line."""
    return ACCENT_KEYS.sub(lambda m: f'{m.group(1)}"{color.lower()}"', theme)


def _write_in_place(path: str, text: str):
    """Replace the content of a file the way an editor does: all or nothing, keeping its mode."""
    mode = os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o644
    handle, temporary = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".gattuccino-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class Btop(Tool):
    name = "btop"
    label = "btop"
    command = "btop"
    help = "Theme btop, the resource monitor, with Catppuccin; it follows the flavor and the accent"

    def theme_path(self, desktop) -> str:
        return f"{desktop.config_dir}/btop/themes/{NAME}.theme"

    def config_path(self, desktop) -> str:
        return f"{desktop.config_dir}/btop/btop.conf"

    def sync(self, context):
        desktop = context.desktop
        theme = _read(theme_file(context.flavor))
        color = palette.color(context.flavor, context.accent)
        text = header("btop theme", context.flavor, context.accent,
                      "# The colors are the ones of the official port, https://github.com/catppuccin/btop,\n"
                      "# with the accent for hi_fg and selected_fg.\n\n") + with_accent(theme, color)
        write_managed(self.theme_path(desktop), text, context.notes)
        self.ask_for_it(context)

    def ask_for_it(self, context):
        """Make btop.conf ask for the theme by its name, remembering what it asked for before."""
        path, state = self.config_path(context.desktop), context.state
        if os.path.islink(path):
            context.notes.append(
                f'{path} is a symlink, so it is not edited: set `color_theme = "{NAME}"` in the file it points to, '
                "and btop has the theme.")
            return
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _write_in_place(path, f'color_theme = "{NAME}"\n')
            state.clear()
            state["created"] = True
            return

        text = _read(path)
        match = LINE.search(text)
        if match and match.group(1) == NAME:
            return   # asked for already
        state.clear()
        if match:
            state["original"] = match.group(1)
            context.notes.append(f'btop.conf had color_theme = "{match.group(1)}": it asks for "{NAME}" now, '
                                 "and gets that back when the tool is turned off.")
            text = text[:match.start()] + f'color_theme = "{NAME}"' + text[match.end():]
        else:
            state["added"] = True
            text = text + ("" if text.endswith("\n") or not text else "\n") + f'color_theme = "{NAME}"\n'
        _write_in_place(path, text)

    def remove(self, context):
        desktop = context.desktop
        remove_managed(self.theme_path(desktop))
        path, state = self.config_path(desktop), context.state
        if os.path.islink(path) or not os.path.exists(path):
            state.clear()
            return
        text = _read(path)
        match = LINE.search(text)
        if match and match.group(1) == NAME:
            if state.get("created") and text.strip() == f'color_theme = "{NAME}"':
                os.remove(path)   # the one line this project made the file of
            elif "original" in state:
                _write_in_place(path, text[:match.start()] + f'color_theme = "{state["original"]}"' + text[match.end():])
            elif state.get("added"):
                _write_in_place(path, (text[:match.start()] + text[match.end() + 1:]))
            else:
                # asked for the theme and nothing was remembered: btop's own is what it falls back to
                _write_in_place(path, text[:match.start()] + 'color_theme = "Default"' + text[match.end():])
        state.clear()
