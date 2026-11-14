"""What the window does with the preferences, apart from drawing them.

A change is checked, written to `preferences.ini` and, if it is one the
extensions change while they run, put into their settings at once. The rest
wait for `apply`, which builds the theme and installs what the preferences say.
"""

import copy

from . import install, live, preferences as prefs, shell_theme, sources, tools
from .desktop import Desktop

ERRORS = (prefs.PreferenceError, install.InstallError, shell_theme.BuildError, sources.SourcesError)


class Controller:
    def __init__(self, desktop: Desktop):
        self.desktop = desktop
        self.fields = prefs.all_fields()
        self.preferences = live.load(desktop)
        self.pending = set()   # what is built into the theme and was changed since the last apply
        self.notes = []        # what the last change had to say, for a toast

    def text(self, name: str) -> str:
        return self.preferences.text(name)

    def visible(self, field: prefs.Field) -> bool:
        return prefs.visible(field, self.preferences)

    def set(self, name: str, text: str):
        """Take a value. Returns what is wrong with it, or None when it was taken."""
        trial = copy.copy(self.preferences)
        try:
            trial.set(name, text)
        except prefs.PreferenceError as e:
            return str(e)
        if getattr(trial, name) == getattr(self.preferences, name):
            return None
        self.preferences = trial
        prefs.save(self.preferences, self.desktop.preferences_path)
        if name in prefs.LIVE_NAMES:
            live.push(self.desktop, self.preferences, only={name})
        elif name in tools.preference_names():
            # A tool in a terminal is themed, or not, at once: that is all it takes
            self.notes = install.sync_tools(self.preferences, self.desktop, log=lambda _line: None)
        else:
            self.pending.add(name)
        return None

    def refresh(self) -> list:
        """Take what the extensions' settings say now; the names that were not what they said."""
        return live.pull(self.desktop, self.preferences)

    def apply(self, log=print):
        """Build and install what the preferences say. Raises one of ERRORS."""
        install.apply(self.preferences, self.desktop, log=log)
        self.pending.clear()
