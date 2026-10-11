"""A throwaway home folder with stand-ins for the GNOME commands, so that the
installer can be run for real without touching the machine it is tested on."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL_VERSION = "49.2"
USER_THEME_UUID = "user-theme@gnome-shell-extensions.gcampax.github.com"

# gsettings, backed by a JSON file. The User Themes schema only exists when the
# test says the extension is installed, system-wide or in the home folder.
GSETTINGS = r'''
import ast, json, os, re, sys
args = sys.argv[1:]
schemadir = None
if args[:1] == ["--schemadir"]:
    schemadir, args = args[1], args[2:]
store_path = os.environ["FAKE_GSETTINGS"]
store = json.load(open(store_path))
command, schema = args[0], args[1]
known = schema in store
if schema == "org.gnome.shell.extensions.user-theme":
    mode = open(os.environ["FAKE_USER_THEMES"]).read().strip()
    known = mode == "system" or (mode == "user" and schemadir is not None
                                 and os.path.exists(schemadir + "/gschemas.compiled"))
if not known:
    sys.exit(f"No such schema “{schema}”")
if command == "list-keys":
    print("\n".join(store[schema]))
elif command == "get":
    value = store[schema][args[2]]
    print("@as []" if value == [] else repr(value))
elif command == "set":
    store[schema][args[2]] = ast.literal_eval(re.sub(r"^@\w+\s+", "", args[3]))
    json.dump(store, open(store_path, "w"))
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(f"gsettings set {schema} {args[2]} {args[3]}\n")
'''

# gnome-extensions: like GNOME Shell, it only knows the extensions that were
# there at "login" (listed in a file by the test).
GNOME_EXTENSIONS = r'''
import json, os, sys
command, uuid = sys.argv[1], sys.argv[2]
known = open(os.environ["FAKE_KNOWN_EXTENSIONS"]).read().split()
if uuid not in known:
    sys.exit(f"Extension “{uuid}” does not exist")
store_path = os.environ["FAKE_GSETTINGS"]
store = json.load(open(store_path))
enabled = store["org.gnome.shell"]["enabled-extensions"]
if command == "enable" and uuid not in enabled:
    enabled.append(uuid)
if command == "disable" and uuid in enabled:
    enabled.remove(uuid)
json.dump(store, open(store_path, "w"))
'''

FLATPAK = r'''
import os, sys
assert sys.argv[1:3] == ["override", "--user"], sys.argv
entries = [a.split("=", 1)[1] for a in sys.argv[3:] if a.startswith("--filesystem=")]
path = os.path.join(os.environ["XDG_DATA_HOME"], "flatpak/overrides/global")
os.makedirs(os.path.dirname(path), exist_ok=True)
lines = open(path).read().splitlines() if os.path.exists(path) else []
if "[Context]" not in lines:
    lines += ["[Context]"]
index = next((i for i, l in enumerate(lines) if l.startswith("filesystems=")), None)
if index is None:
    lines.insert(lines.index("[Context]") + 1, "filesystems=" + ";".join(entries) + ";")
else:
    lines[index] += ";".join(entries) + ";"
open(path, "w").write("\n".join(lines) + "\n")
'''

GNOME_SHELL = 'import os\nprint("GNOME Shell " + open(os.environ["FAKE_SHELL_VERSION"]).read().strip())\n'


def test_sources():
    """GNOME Shell's data/theme for SHELL_VERSION, downloaded once into tests/.cache;
    None when it cannot be had (no network)."""
    from gattuccino import sources
    try:
        return sources.theme_sources(SHELL_VERSION, os.path.join(ROOT, "tests", ".cache"), log=lambda _: None)
    except sources.SourcesError:
        return None


class FakeHome:
    def __init__(self, user_themes="user", shell_version=SHELL_VERSION, commands=("gsettings", "gnome-extensions", "flatpak", "gnome-shell")):
        self.root = tempfile.mkdtemp(prefix="gattuccino-home-")
        self.home = f"{self.root}/home"
        self.bin = f"{self.root}/bin"
        os.makedirs(self.home)
        os.makedirs(self.bin)
        self.config = f"{self.home}/.config"
        self.data = f"{self.home}/.local/share"
        self.cache = f"{self.home}/.cache"
        self.themes = f"{self.home}/.themes"
        self.extensions = f"{self.data}/gnome-shell/extensions"
        self.flatpak_file = f"{self.data}/flatpak/overrides/global"
        self._files = {name: f"{self.root}/{name}" for name in ("gsettings.json", "user-themes", "known-extensions", "shell-version", "log")}
        self.write_settings({
            "org.gnome.desktop.interface": {"accent-color": "teal", "color-scheme": "default", "gtk-theme": "Adwaita"},
            "org.gnome.shell": {"enabled-extensions": [USER_THEME_UUID], "disabled-extensions": []},
            "org.gnome.shell.extensions.user-theme": {"name": "Yaru"},
        })
        self.set_user_themes(user_themes)
        self.set_known_extensions([USER_THEME_UUID])
        self.set_shell_version(shell_version)
        open(self._files["log"], "w").close()

        scripts = {"gsettings": GSETTINGS, "gnome-extensions": GNOME_EXTENSIONS, "flatpak": FLATPAK, "gnome-shell": GNOME_SHELL}
        for name in commands:
            path = f"{self.bin}/{name}"
            with open(path, "w") as f:
                f.write(f"#!{sys.executable}\n" + textwrap.dedent(scripts[name]))
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        # git, sassc and the like still come from the real system
        self.env = dict(os.environ, HOME=self.home, PATH=f"{self.bin}:{os.environ['PATH']}",
                        XDG_CONFIG_HOME=self.config, XDG_DATA_HOME=self.data, XDG_CACHE_HOME=self.cache,
                        XDG_DATA_DIRS=f"{self.root}/usr/share",
                        FAKE_GSETTINGS=self._files["gsettings.json"], FAKE_USER_THEMES=self._files["user-themes"],
                        FAKE_KNOWN_EXTENSIONS=self._files["known-extensions"],
                        FAKE_SHELL_VERSION=self._files["shell-version"], FAKE_LOG=self._files["log"])

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # --- What the "machine" looks like -----------------------------------

    def write_settings(self, store):
        with open(self._files["gsettings.json"], "w") as f:
            json.dump(store, f)

    def settings(self, schema, key):
        with open(self._files["gsettings.json"]) as f:
            return json.load(f)[schema][key]

    def set_setting(self, schema, key, value):
        with open(self._files["gsettings.json"]) as f:
            store = json.load(f)
        store[schema][key] = value
        self.write_settings(store)

    def set_user_themes(self, mode):
        """'user': installed in the home folder; 'system': packaged; 'no': not installed."""
        with open(self._files["user-themes"], "w") as f:
            f.write(mode)
        schemas = f"{self.extensions}/{USER_THEME_UUID}/schemas"
        if mode == "user":
            os.makedirs(schemas, exist_ok=True)
            open(f"{schemas}/gschemas.compiled", "w").close()

    def set_known_extensions(self, uuids):
        with open(self._files["known-extensions"], "w") as f:
            f.write("\n".join(uuids))

    def login(self):
        """A new login: GNOME Shell now knows every extension in the home folder."""
        self.set_known_extensions(os.listdir(self.extensions) if os.path.isdir(self.extensions) else [])

    def set_shell_version(self, version):
        with open(self._files["shell-version"], "w") as f:
            f.write(version)

    def seed_sources(self, theme_dir, version=SHELL_VERSION):
        """Put the stylesheets in the cache, as if they had been downloaded before."""
        shutil.copytree(theme_dir, f"{self.cache}/gattuccino/gnome-shell-{version}/theme")

    def log(self):
        with open(self._files["log"]) as f:
            return f.read()

    # --- Running the command ----------------------------------------------

    def run(self, *args, input=None):
        return subprocess.run([sys.executable, os.path.join(ROOT, "gattuccino"), *args],
                              capture_output=True, text=True, env=self.env, input=input)

    def ok(self, *args, input=None):
        result = self.run(*args, input=input)
        assert result.returncode == 0, f"{args} failed:\n{result.stdout}\n{result.stderr}"
        return result.stdout

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()
