"""Claude Code, which reads custom themes from the folder `themes` of its configuration
(`$CLAUDE_CONFIG_DIR`, or `~/.claude`): a file `NAME.json` with a name, a `base` theme
(`dark` or `light`) and the `overrides` of the colors it changes, chosen by `"theme":
"custom:NAME"` in `settings.json`.

There is no official Catppuccin port for it, so the theme is made here, from the palette:
the brand color (the spinner, the name of Claude, the mascot) takes the accent; the
permission prompts, suggestions and the IDE are blue; success, error and warning are green,
red and yellow; the backgrounds of diffs are those colors in a little of the base, and the
messages sit on surface0.

A theme file has one base, so there is one file, `gattuccino.json`, which is the flavor in
use (Latte on `light`, the others on `dark`) and is written again when the style or the
flavor changes: Claude Code watches the folder, so a session that is open follows.

`settings.json` is touched in one place, `theme`, which is pointed at `custom:gattuccino`;
what it was is remembered and put back when the tool is turned off, unless it was changed
since. A `settings.json` that is a symlink, or is not valid JSON, is not written: a note
says what to set.
"""

import json
import os

from .. import palette
from . import Tool, remove_managed, same_content, write_managed

NAME = "gattuccino"
THEME = f"custom:{NAME}"


def mix(first: str, second: str, share: float) -> str:
    """`first` with `share` (0 to 1) of `second` blended in, as a hex color."""
    a, b = first.lstrip("#"), second.lstrip("#")
    parts = [round(int(a[i:i + 2], 16) * (1 - share) + int(b[i:i + 2], 16) * share) for i in (0, 2, 4)]
    return "#" + "".join(f"{p:02x}" for p in parts)


def overrides(flavor: str, accent: str) -> dict:
    """The colors of Claude Code, by its names for them (the ones it does not know are ignored by it)."""
    c = lambda name: palette.color(flavor, name).lower()  # noqa: E731
    base, text = c("base"), c("text")
    accent_color = c(accent)
    shimmer = lambda color: mix(color, text, 0.3)  # noqa: E731
    tint = lambda color, share: mix(base, c(color), share)  # noqa: E731

    colors = {
        # the brand: the accent
        "claude": accent_color, "claudeShimmer": shimmer(accent_color),
        "clawd_body": accent_color, "clawd_background": c("crust"), "briefLabelClaude": accent_color,
        # text and borders
        "text": text, "inverseText": base, "inactive": c("overlay2"), "inactiveShimmer": c("subtext0"),
        "subtle": c("surface2"), "promptBorder": c("overlay0"), "promptBorderShimmer": c("overlay1"),
        # prompts and modes
        "permission": c("blue"), "permissionShimmer": c("lavender"), "suggestion": c("blue"),
        "remember": c("blue"), "ide": c("sapphire"), "briefLabelYou": c("blue"),
        "claudeBlue_FOR_SYSTEM_SPINNER": c("blue"), "claudeBlueShimmer_FOR_SYSTEM_SPINNER": c("lavender"),
        "planMode": c("teal"), "autoAccept": c("mauve"), "autoAcceptShimmer": shimmer(c("mauve")),
        "skill": c("mauve"), "merged": c("mauve"), "effortUltra": c("mauve"),
        "bashBorder": c("pink"), "background": c("sapphire"),
        "fastMode": c("peach"), "fastModeShimmer": shimmer(c("peach")),
        "rate_limit_fill": c("blue"), "rate_limit_empty": c("surface1"),
        # states
        "success": c("green"), "error": c("red"), "warning": c("yellow"), "warningShimmer": c("peach"),
        # diffs: the colors in a little of the base, the words in more
        "diffAdded": tint("green", 0.25), "diffRemoved": tint("red", 0.25),
        "diffAddedDimmed": tint("green", 0.14), "diffRemovedDimmed": tint("red", 0.14),
        "diffAddedWord": tint("green", 0.5), "diffRemovedWord": tint("red", 0.5),
        # what messages sit on
        "userMessageBackground": c("surface0"), "userMessageBackgroundHover": c("surface1"),
        "composerSidebarBackground": c("mantle"), "selectionBg": c("surface2"),
        "bashMessageBackgroundColor": c("mantle"), "memoryBackgroundColor": tint("teal", 0.12),
        # the subagents
        "red_FOR_SUBAGENTS_ONLY": c("red"), "blue_FOR_SUBAGENTS_ONLY": c("blue"),
        "green_FOR_SUBAGENTS_ONLY": c("green"), "yellow_FOR_SUBAGENTS_ONLY": c("yellow"),
        "purple_FOR_SUBAGENTS_ONLY": c("mauve"), "orange_FOR_SUBAGENTS_ONLY": c("peach"),
        "pink_FOR_SUBAGENTS_ONLY": c("pink"), "cyan_FOR_SUBAGENTS_ONLY": c("teal"),
        "professionalBlue": c("blue"), "chromeYellow": c("yellow"),
    }
    for word, color in (("red", "red"), ("orange", "peach"), ("yellow", "yellow"), ("green", "green"),
                        ("blue", "blue"), ("indigo", "lavender"), ("violet", "mauve")):
        colors[f"rainbow_{word}"] = c(color)
        colors[f"rainbow_{word}_shimmer"] = shimmer(c(color))
    return colors


def theme_text(flavor: str, accent: str) -> str:
    """The theme as a JSON file. JSON has no comments, so the marker is a first key, which Claude Code ignores."""
    theme = {
        "gattuccino": f"written by gattuccino (flavor={flavor}, accent={accent}), and rewritten whenever "
                      "the flavor or the accent changes; edits are overwritten",
        "name": "Gattuccino",
        "base": "dark" if palette.DARK[flavor] else "light",
        "overrides": overrides(flavor, accent),
    }
    return json.dumps(theme, indent=2) + "\n"


class ClaudeCode(Tool):
    name = "claude_code"
    label = "Claude Code"
    command = "claude"
    help = ("Theme Claude Code with Catppuccin; it follows the flavor and the accent "
            "(its brand color), and the style of the desktop")

    def folder(self, desktop) -> str:
        configured = desktop.environment.get("CLAUDE_CONFIG_DIR")
        return configured or f"{desktop.home}/.claude"

    def theme_path(self, desktop) -> str:
        return f"{self.folder(desktop)}/themes/{NAME}.json"

    def settings_path(self, desktop) -> str:
        return f"{self.folder(desktop)}/settings.json"

    def sync(self, context):
        desktop = context.desktop
        path = self.theme_path(desktop)
        text = theme_text(context.flavor, context.accent)
        if not same_content(path, text):
            write_managed(path, text, context.notes)
        self.choose(context)

    # --- settings.json ------------------------------------------------------

    def load(self, path: str):
        """The settings as a dict, `{}` when there is no file, None when they cannot be taken as they are."""
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def save(self, path: str, data: dict):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def choose(self, context):
        """Point `theme` of settings.json at the theme, once, and remember what it was."""
        path, state = self.settings_path(context.desktop), context.state
        if os.path.islink(path):
            context.notes.append(f"{path} is a symlink, so it is not edited: set \"theme\": \"{THEME}\" in "
                                 "the file it points to, or choose the theme with /theme in Claude Code.")
            return
        data = self.load(path)
        if data is None:
            context.notes.append(f"{path} is not a JSON object, so it is not edited: choose the theme with "
                                 "/theme in Claude Code.")
            return
        if data.get("theme") == THEME:
            return
        state.clear()
        state["previous"] = data.get("theme")   # None when there was none
        data["theme"] = THEME
        self.save(path, data)

    def remove(self, context):
        desktop, state = context.desktop, context.state
        path = self.settings_path(desktop)
        if not os.path.islink(path) and "previous" in state:
            data = self.load(path)
            if data is not None and data.get("theme") == THEME:   # changed since: left as it is
                if state["previous"] is None:
                    del data["theme"]
                else:
                    data["theme"] = state["previous"]
                self.save(path, data)
        state.clear()
        remove_managed(self.theme_path(desktop))
