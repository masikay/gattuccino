"""Applies the preferences to the user's session, and takes them back out.

Everything is built first, so that a failure there leaves the session as it
was. What gets replaced along the way (the selected shell theme, a gtk.css of
your own, a few settings) is remembered in the state file, and put back by
`uninstall` or when a preference is turned off again.
"""

import filecmp
import json
import os
import shutil
import time

from . import gtk_theme, palette, shell_theme, sources
from .desktop import INTERFACE_SCHEMA, USER_THEME_SCHEMA, USER_THEME_UUID, Desktop
from .preferences import AUTO, Preferences

# install.py is src/gattuccino/install.py: three levels up is the repo root.
EXTENSIONS_SOURCE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "extensions")
FLOATING_PANEL_UUID = "floating-panel@gattuccino"
ACCENT_UUID = "catppuccin-accent@gattuccino"
# Names this project used before it was renamed. Nothing installs under these
# any more, but apply() and uninstall() still remove them, so an earlier
# install is cleaned up instead of left behind, orphaned, next to the new one.
LEGACY_FLOATING_PANEL_UUID = "floating-panel@gnome-catppuccin"
LEGACY_ACCENT_UUID = "catppuccin-accent@gnome-catppuccin"

GTK_BACKUP_SUFFIX = ".before-gattuccino"
LEGACY_GTK_BACKUP_SUFFIX = ".before-gnome-catppuccin"
FLATPAK_FILESYSTEMS = ["xdg-config/gtk-4.0:ro", "xdg-config/gtk-3.0:ro"]


class InstallError(Exception):
    pass


# --- State -------------------------------------------------------------------

def _load_state(desktop: Desktop) -> dict:
    try:
        with open(desktop.state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    state.setdefault("previous", {})  # settings as they were before the first apply
    state.setdefault("flatpak", [])   # Flatpak folders this project opened
    return state


def _save_state(desktop: Desktop, state: dict):
    os.makedirs(os.path.dirname(desktop.state_path), exist_ok=True)
    with open(desktop.state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


# --- What to build -----------------------------------------------------------

def shell_options(preferences: Preferences) -> shell_theme.ShellOptions:
    opacity = lambda value: None if value is None or value >= 1 else value  # noqa: E731
    return shell_theme.ShellOptions(
        panel_opacity=opacity(preferences.panel_opacity),
        popup_opacity=opacity(preferences.popup_opacity),
        floating_panel=preferences.floating_panel,
        panel_gap=preferences.panel_gap,
        panel_radius=preferences.panel_radius,
        # Unlike the others, "opaque" here differs from "not set": it is how a
        # translucent floating bar turns solid when it docks.
        docked_panel_opacity=preferences.docked_panel_opacity,
        dock_like_panel=preferences.dock_like_panel,
        accent_selection=preferences.accent_selection,
    )


def shell_accents(preferences: Preferences):
    """Accents to build a shell theme for: all nine of the Settings picker when
    following it, since a theme cannot change its accent on its own."""
    if preferences.follows_picker:
        return list(palette.SETTINGS_ACCENTS.values())
    return [preferences.accent]


def resolve_shell_version(preferences: Preferences) -> str:
    if preferences.shell_version != AUTO:
        return preferences.shell_version
    version = sources.installed_version()
    if not version:
        raise InstallError("Could not find out the GNOME Shell version (is `gnome-shell` installed?). "
                           "Set it with: gattuccino configure --shell-version VERSION")
    sources.check_version(version)
    return version


def shell_flavors(preferences: Preferences):
    """Latte for the light style, and the chosen flavor for the dark one."""
    return [palette.LIGHT_FLAVOR, preferences.flavor]


def shell_theme_names(preferences: Preferences):
    return [shell_theme.theme_name(f, a) for f in shell_flavors(preferences) for a in shell_accents(preferences)]


def build_shell_themes(preferences: Preferences, cache_dir: str, log=print):
    """Returns (GNOME Shell version, {theme name: (flavor, accent, stylesheet)})."""
    version = resolve_shell_version(preferences)
    theme_dir = sources.theme_sources(version, cache_dir, log)
    options = shell_options(preferences)
    accents = shell_accents(preferences)
    flavors = shell_flavors(preferences)
    log(f"Building the shell theme for GNOME Shell {version} "
        f"({' and '.join(flavors)}, {len(accents)} accent{'s' if len(accents) > 1 else ''})...")
    return version, {
        shell_theme.theme_name(flavor, accent):
            (flavor, accent, shell_theme.build_css(theme_dir, flavor, accent, options))
        for flavor in flavors for accent in accents
    }


def current_accent(preferences: Preferences, desktop: Desktop) -> str:
    """The Catppuccin accent in effect right now."""
    if not preferences.follows_picker:
        return preferences.accent
    picked = desktop.gsettings_get(INTERFACE_SCHEMA, "accent-color")
    return palette.SETTINGS_ACCENTS.get(picked, "blue")


def dark_style(desktop: Desktop) -> bool:
    """Whether the dark style is picked in Settings > Appearance right now."""
    scheme = desktop.gsettings_get(INTERFACE_SCHEMA, "color-scheme")
    return scheme is None or scheme == "prefer-dark"


def current_flavor(preferences: Preferences, desktop: Desktop) -> str:
    """The flavor in effect right now: it follows the style picked in Settings."""
    return preferences.flavor if dark_style(desktop) else palette.LIGHT_FLAVOR


# --- Shell theme -------------------------------------------------------------

def _is_own_theme(desktop: Desktop, name: str) -> bool:
    if not name:
        return False
    return any(os.path.exists(f"{desktop.themes_dir}/{name}/{marker}")
              for marker in (shell_theme.MARKER, *shell_theme.LEGACY_MARKERS))


def _own_themes(desktop: Desktop):
    try:
        names = sorted(os.listdir(desktop.themes_dir))
    except OSError:
        return []
    return [name for name in names if _is_own_theme(desktop, name)]


def _check_theme_folders(desktop: Desktop, names):
    for name in names:
        path = f"{desktop.themes_dir}/{name}"
        if os.path.lexists(path) and not _is_own_theme(desktop, name):
            raise InstallError(f"{path} exists and was not created by gattuccino. "
                               "Move it away and apply again.")


def _install_shell_themes(desktop: Desktop, preferences: Preferences, version: str, themes: dict, state, notes):
    selected = shell_theme.theme_name(current_flavor(preferences, desktop), current_accent(preferences, desktop))
    schema_args = desktop.user_theme_schema_args()
    current = desktop.gsettings_get(USER_THEME_SCHEMA, "name", schema_args) if schema_args is not None else None
    if current is not None and "user-theme" not in state["previous"] and not _is_own_theme(desktop, current):
        state["previous"]["user-theme"] = current

    for name in _own_themes(desktop):
        shutil.rmtree(f"{desktop.themes_dir}/{name}")
    for name, (flavor, accent, css) in themes.items():
        shell_theme.write_theme(f"{desktop.themes_dir}/{name}", css, flavor, accent, version,
                                dock_accent=preferences.accent_selection)

    if schema_args is None:
        notes.append("The User Themes extension is not installed, so the shell theme is not in use yet. "
                     "Install it (package gnome-shell-extension-user-theme or gnome-shell-extensions, "
                     "or https://extensions.gnome.org/extension/19/user-themes/), then apply again.")
        return False
    # GNOME Shell only reads a theme when it is selected: go through "no theme"
    # so that a rebuilt theme of the same name is loaded again.
    desktop.gsettings_set(USER_THEME_SCHEMA, "name", "", schema_args)
    desktop.gsettings_set(USER_THEME_SCHEMA, "name", selected, schema_args)
    return desktop.enable_extension(USER_THEME_UUID)


def _remove_shell_themes(desktop: Desktop, state):
    schema_args = desktop.user_theme_schema_args()
    if schema_args is not None:
        current = desktop.gsettings_get(USER_THEME_SCHEMA, "name", schema_args)
        if _is_own_theme(desktop, current):
            desktop.gsettings_set(USER_THEME_SCHEMA, "name", state["previous"].get("user-theme", ""), schema_args)
    state["previous"].pop("user-theme", None)
    for name in _own_themes(desktop):
        shutil.rmtree(f"{desktop.themes_dir}/{name}")


# --- Application colors ------------------------------------------------------

def _is_own_file(path: str) -> bool:
    markers = (gtk_theme.MARKER, gtk_theme.LEGACY_MARKER)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(max(len(m) for m in markers))
    except OSError:
        return False
    return any(head.startswith(m) for m in markers)


def _own_gtk_files(directory: str):
    """gtk.css and the gattuccino-*.css files in a folder, if this project wrote them
    (including the ones an earlier version, under its old name, wrote)."""
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    prefixes = ("gattuccino-", "gnome-catppuccin-")
    return [name for name in names
            if (name == "gtk.css" or (name.startswith(prefixes) and name.endswith(".css")))
            and _is_own_file(f"{directory}/{name}")]


def gtk_files(preferences: Preferences, desktop: Desktop):
    return gtk_theme.files(preferences.flavor, dark_style(desktop), current_accent(preferences, desktop),
                           preferences.accent, preferences.accent_selection)


def _install_gtk(desktop: Desktop, preferences: Preferences, notes):
    for folder, contents in gtk_files(preferences, desktop).items():
        directory = f"{desktop.config_dir}/{folder}"
        os.makedirs(directory, exist_ok=True)
        # e.g. the colors of the dark flavor chosen before
        for name in _own_gtk_files(directory):
            if name not in contents:
                os.remove(f"{directory}/{name}")
        gtk_css = f"{directory}/gtk.css"
        if os.path.lexists(gtk_css) and not _is_own_file(gtk_css):
            backup = gtk_css + GTK_BACKUP_SUFFIX
            if os.path.lexists(backup):  # never overwrite an earlier backup
                backup += time.strftime(".%Y%m%d-%H%M%S")
            os.replace(gtk_css, backup)
            notes.append(f"Your own {gtk_css} was kept as {os.path.basename(backup)}.")
        for name, text in contents.items():
            with open(f"{directory}/{name}", "w", encoding="utf-8") as f:
                f.write(text)


def _remove_gtk(desktop: Desktop):
    for folder in ("gtk-4.0", "gtk-3.0"):
        directory = f"{desktop.config_dir}/{folder}"
        for name in _own_gtk_files(directory):
            os.remove(f"{directory}/{name}")
        for suffix in (GTK_BACKUP_SUFFIX, LEGACY_GTK_BACKUP_SUFFIX):
            backup = f"{directory}/gtk.css{suffix}"
            if os.path.lexists(backup) and not os.path.lexists(f"{directory}/gtk.css"):
                os.replace(backup, f"{directory}/gtk.css")
                break


def _find_gtk3_theme(desktop: Desktop, name: str) -> bool:
    return any(os.path.isdir(f"{directory}/{name}/gtk-3.0") for directory in desktop.gtk_theme_dirs)


def _set_remembering(desktop: Desktop, state, key: str, value: str):
    """Set an interface setting, remembering what it was before the first change."""
    current = desktop.gsettings_get(INTERFACE_SCHEMA, key)
    if current is None:
        return
    state["previous"].setdefault(key, current)
    if current != value:
        desktop.gsettings_set(INTERFACE_SCHEMA, key, value)


def _restore(desktop: Desktop, state, key: str):
    if key in state["previous"]:
        desktop.gsettings_set(INTERFACE_SCHEMA, key, state["previous"].pop(key))


def _apply_application_settings(desktop: Desktop, state, notes):
    # The style is the user's choice in Settings, and picks the flavor: it is
    # no longer set here. Earlier versions did, and remembered it.
    state["previous"].pop("color-scheme", None)

    # The catppuccin-accent extension switches between the two along with the style
    if all(_find_gtk3_theme(desktop, name) for name in ("adw-gtk3", "adw-gtk3-dark")):
        _set_remembering(desktop, state, "gtk-theme", "adw-gtk3-dark" if dark_style(desktop) else "adw-gtk3")
    else:
        notes.append("GTK 3 applications keep their own colors: they only follow with the adw-gtk3 "
                     "theme (https://github.com/lassekongo83/adw-gtk3). Install it and apply again "
                     "to have adw-gtk3 or adw-gtk3-dark selected.")


# --- Flatpak -----------------------------------------------------------------

def _open_flatpak(desktop: Desktop, state, notes):
    if not desktop.has("flatpak"):
        notes.append("Flatpak is not installed: nothing to set up for it.")
        return
    allowed = {entry.split(":")[0] for entry in desktop.flatpak_filesystems()}
    for entry in FLATPAK_FILESYSTEMS:
        if entry.split(":")[0] in allowed:
            continue
        if desktop.run("flatpak", "override", "--user", f"--filesystem={entry}").returncode == 0:
            state["flatpak"].append(entry)
        else:
            notes.append(f"Could not let Flatpak applications read {entry.split(':')[0]}.")
    notes.append("Flatpak GTK 3 applications also need the theme itself: "
                 "flatpak install org.gtk.Gtk3theme.adw-gtk3 org.gtk.Gtk3theme.adw-gtk3-dark")


def _close_flatpak(desktop: Desktop, state):
    if state["flatpak"]:
        desktop.flatpak_remove_filesystems(state["flatpak"])
        state["flatpak"] = []


# --- Extensions --------------------------------------------------------------

def _same_tree(a: str, b: str) -> bool:
    if not os.path.isdir(b):
        return False
    comparison = filecmp.dircmp(a, b)
    if comparison.left_only or comparison.right_only or comparison.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, comparison.common_files, shallow=False)
    return not mismatch and not errors and all(
        _same_tree(f"{a}/{name}", f"{b}/{name}") for name in comparison.common_dirs)


def _install_extension(desktop: Desktop, uuid: str) -> bool:
    """Copy and enable an extension. Returns True if a new login is needed for it."""
    source, destination = f"{EXTENSIONS_SOURCE}/{uuid}", f"{desktop.extensions_dir}/{uuid}"
    changed = not _same_tree(source, destination)
    if changed:
        shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(source, destination)
    # GNOME Shell keeps running the code it loaded at login
    return desktop.enable_extension(uuid) or changed


def _remove_extension(desktop: Desktop, uuid: str):
    destination = f"{desktop.extensions_dir}/{uuid}"
    if os.path.isdir(destination):
        desktop.disable_extension(uuid)
        shutil.rmtree(destination)


# --- Apply and uninstall -----------------------------------------------------

def apply(preferences: Preferences, desktop: Desktop, log=print):
    if not desktop.has("gsettings"):
        raise InstallError("gsettings was not found: this needs a GNOME session.")

    # Build first: nothing is touched if this fails
    version, themes = None, {}
    if preferences.shell_theme:
        shell_theme.require_compiler()
        _check_theme_folders(desktop, shell_theme_names(preferences))
        version, themes = build_shell_themes(preferences, desktop.cache_dir, log)

    state = _load_state(desktop)
    notes, relogin = [], False

    if preferences.shell_theme:
        relogin |= _install_shell_themes(desktop, preferences, version, themes, state, notes)
        log(f"Installed {len(themes)} shell theme{'s' if len(themes) > 1 else ''} in {desktop.themes_dir}")
    else:
        _remove_shell_themes(desktop, state)

    if preferences.gtk_theme:
        _install_gtk(desktop, preferences, notes)
        _apply_application_settings(desktop, state, notes)
        log(f"Installed the application colors in {desktop.config_dir}/gtk-4.0 and gtk-3.0")
    else:
        _remove_gtk(desktop)
        _restore(desktop, state, "color-scheme")
        _restore(desktop, state, "gtk-theme")

    if preferences.flatpak and preferences.gtk_theme:
        _open_flatpak(desktop, state, notes)
    else:
        _close_flatpak(desktop, state)

    wanted = {
        FLOATING_PANEL_UUID: preferences.shell_theme and preferences.floating_panel,
        # Follows the style, and the accent when asked to, for whichever of the two is installed
        ACCENT_UUID: preferences.shell_theme or preferences.gtk_theme,
    }
    for uuid, want in wanted.items():
        if want:
            relogin |= _install_extension(desktop, uuid)
            log(f"Installed the extension {uuid}")
        else:
            _remove_extension(desktop, uuid)
    # Clean up what an earlier version, under this project's old name, installed
    for uuid in (LEGACY_FLOATING_PANEL_UUID, LEGACY_ACCENT_UUID):
        _remove_extension(desktop, uuid)

    _save_state(desktop, state)
    for note in notes:
        log(f"Note: {note}")
    if preferences.gtk_theme:
        log("Applications show the new colors the next time they are started.")
    if relogin:
        log("Log out and back in to load the extensions.")


def uninstall(desktop: Desktop, log=print):
    state = _load_state(desktop)
    _remove_shell_themes(desktop, state)
    _remove_gtk(desktop)
    _restore(desktop, state, "color-scheme")
    _restore(desktop, state, "gtk-theme")
    _close_flatpak(desktop, state)
    for uuid in (FLOATING_PANEL_UUID, ACCENT_UUID, LEGACY_FLOATING_PANEL_UUID, LEGACY_ACCENT_UUID):
        _remove_extension(desktop, uuid)
    for path in (desktop.state_path,):
        if os.path.exists(path):
            os.remove(path)
    shutil.rmtree(desktop.cache_dir, ignore_errors=True)
    log("Removed the shell themes, the application colors and the extensions, and put back "
        "the settings that were changed.")
    log(f"Your preferences are kept in {desktop.preferences_path}.")
