"""The user's session: where things go, and the GNOME commands used to set it up."""

import ast
import os
import re
import shutil
import subprocess

USER_THEME_UUID = "user-theme@gnome-shell-extensions.gcampax.github.com"
USER_THEME_SCHEMA = "org.gnome.shell.extensions.user-theme"
INTERFACE_SCHEMA = "org.gnome.desktop.interface"
SHELL_SCHEMA = "org.gnome.shell"


class Desktop:
    def __init__(self, environment=None):
        env = os.environ if environment is None else environment
        self.environment = env
        self.home = env.get("HOME") or os.path.expanduser("~")
        config = env.get("XDG_CONFIG_HOME") or f"{self.home}/.config"
        data = env.get("XDG_DATA_HOME") or f"{self.home}/.local/share"
        cache = env.get("XDG_CACHE_HOME") or f"{self.home}/.cache"
        self.data_dirs = [d for d in (env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if d]

        self.config_dir = config
        self.themes_dir = f"{self.home}/.themes"
        self.extensions_dir = f"{data}/gnome-shell/extensions"
        self.flatpak_overrides = f"{data}/flatpak/overrides/global"
        self.cache_dir = f"{cache}/gattuccino"
        # Earlier versions, under this project's old name, kept their own
        # folder here; move it over so preferences and state survive the rename.
        own_dir = f"{config}/gattuccino"
        legacy_dir = f"{config}/gnome-catppuccin"
        if not os.path.exists(own_dir) and os.path.isdir(legacy_dir):
            try:
                os.rename(legacy_dir, own_dir)
            except OSError:
                pass
        self.preferences_path = f"{own_dir}/preferences.ini"
        self.state_path = f"{own_dir}/state.json"
        # Where a GTK 3 theme can be installed
        self.gtk_theme_dirs = [self.themes_dir, f"{data}/themes"] + [f"{d}/themes" for d in self.data_dirs]

    # --- Commands ---------------------------------------------------------

    def has(self, command: str) -> bool:
        return shutil.which(command, path=self.environment.get("PATH")) is not None

    def run(self, *command):
        if not self.has(command[0]):
            return subprocess.CompletedProcess(command, 127, "", f"{command[0]}: not found")
        try:
            return subprocess.run(command, capture_output=True, text=True, env=self.environment)
        except OSError as e:
            return subprocess.CompletedProcess(command, 127, "", str(e))

    # --- GSettings --------------------------------------------------------

    def gsettings_get(self, schema: str, key: str, schema_args=()):
        """Value of a key as a Python value, or None if it cannot be read."""
        result = self.run("gsettings", *schema_args, "get", schema, key)
        if result.returncode != 0:
            return None
        try:
            # GVariant text: 'a string', ['a', 'list'], or "@as []" for an empty list
            return ast.literal_eval(re.sub(r"^@\w+\s+", "", result.stdout.strip()))
        except (ValueError, SyntaxError):
            return None

    def gsettings_set(self, schema: str, key: str, value, schema_args=()) -> bool:
        text = repr(value) if value != [] else "@as []"
        return self.run("gsettings", *schema_args, "set", schema, key, text).returncode == 0

    def user_theme_schema_args(self):
        """Extra gsettings arguments that reach the User Themes settings, or None
        if the extension is not installed."""
        if self.run("gsettings", "list-keys", USER_THEME_SCHEMA).returncode == 0:
            return ()
        # Installed from extensions.gnome.org: its schema is in its own folder
        schemas = f"{self.extensions_dir}/{USER_THEME_UUID}/schemas"
        if os.path.exists(f"{schemas}/gschemas.compiled"):
            return ("--schemadir", schemas)
        return None

    # --- Extensions -------------------------------------------------------

    def enable_extension(self, uuid: str) -> bool:
        """Enable an extension. Returns True if that only takes effect at the next login."""
        if self.run("gnome-extensions", "enable", uuid).returncode == 0:
            return False
        # GNOME Shell only notices newly copied extensions at login: put it on
        # the list of extensions to enable then.
        disabled = self.gsettings_get(SHELL_SCHEMA, "disabled-extensions") or []
        if uuid in disabled:
            self.gsettings_set(SHELL_SCHEMA, "disabled-extensions", [u for u in disabled if u != uuid])
        enabled = self.gsettings_get(SHELL_SCHEMA, "enabled-extensions") or []
        if uuid not in enabled:
            self.gsettings_set(SHELL_SCHEMA, "enabled-extensions", enabled + [uuid])
        return True

    def disable_extension(self, uuid: str):
        self.run("gnome-extensions", "disable", uuid)
        enabled = self.gsettings_get(SHELL_SCHEMA, "enabled-extensions") or []
        if uuid in enabled:
            self.gsettings_set(SHELL_SCHEMA, "enabled-extensions", [u for u in enabled if u != uuid])

    # --- Flatpak ----------------------------------------------------------
    # `flatpak override` can add a folder to what applications may read, but
    # not take one back, so removal edits its file. It is a plain key file:
    #
    #   [Context]
    #   filesystems=xdg-config/gtk-4.0:ro;~/Games;

    def flatpak_filesystems(self):
        """Folders every Flatpak application of this user is already allowed to read."""
        try:
            with open(self.flatpak_overrides, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            return []
        section = None
        for line in lines:
            if line.startswith("["):
                section = line.strip()
            elif section == "[Context]" and line.startswith("filesystems="):
                return [entry for entry in line.split("=", 1)[1].split(";") if entry]
        return []

    def flatpak_remove_filesystems(self, entries):
        try:
            with open(self.flatpak_overrides, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            return
        result, section = [], None
        for line in lines:
            if line.startswith("["):
                section = line.strip()
            elif section == "[Context]" and line.startswith("filesystems="):
                kept = [e for e in line.split("=", 1)[1].split(";") if e and e not in entries]
                if not kept:
                    continue
                line = "filesystems=" + ";".join(kept) + ";"
            result.append(line)

        # Drop sections left without keys, and the file if nothing is left
        cleaned = []
        for i, line in enumerate(result):
            if line.startswith("["):
                rest = result[i + 1:]
                following = next((l for l in rest if l.strip()), "[")
                if following.startswith("["):
                    continue
            # a removed section leaves its blank separator line behind
            if line.strip() or (cleaned and cleaned[-1].strip()):
                cleaned.append(line)
        while cleaned and not cleaned[-1].strip():
            cleaned.pop()
        if not cleaned:
            os.remove(self.flatpak_overrides)
            return
        with open(self.flatpak_overrides, "w", encoding="utf-8") as f:
            f.write("\n".join(cleaned) + "\n")
