"""Runs the real command in a throwaway home folder, from first apply to uninstall."""

import os
import unittest

from gattuccino import palette, shell_theme

from .support import SHELL_VERSION, USER_THEME_UUID, FakeHome, test_sources

SOURCES = test_sources()
FLOATING = "floating-panel@gattuccino"
ACCENT = "catppuccin-accent@gattuccino"
INTERFACE, SHELL, USER_THEME = "org.gnome.desktop.interface", "org.gnome.shell", "org.gnome.shell.extensions.user-theme"


@unittest.skipUnless(SOURCES, "the GNOME Shell stylesheets could not be downloaded")
@unittest.skipUnless(shell_theme.find_compiler(), "no Sass compiler")
class InstallTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        self.home.seed_sources(SOURCES)
        self.addCleanup(self.home.close)

    def themes(self):
        return sorted(os.listdir(self.home.themes)) if os.path.isdir(self.home.themes) else []

    def test_from_first_apply_to_uninstall(self):
        home = self.home
        # What is there before: a gtk.css of the user's own, a Flatpak folder, adw-gtk3
        os.makedirs(f"{home.config}/gtk-4.0")
        with open(f"{home.config}/gtk-4.0/gtk.css", "w") as f:
            f.write("/* mine */\n")
        os.makedirs(os.path.dirname(home.flatpak_file))
        with open(home.flatpak_file, "w") as f:
            f.write("[Context]\nfilesystems=~/Games;\n\n[Environment]\nFOO=bar\n")
        for theme in ("adw-gtk3", "adw-gtk3-dark"):
            os.makedirs(f"{home.data}/themes/{theme}/gtk-3.0")

        # --- Dark style in Settings: Mocha, accent following the picker (teal), everything on ---
        home.set_setting(INTERFACE, "color-scheme", "prefer-dark")
        out = home.ok("configure", "--flavor", "mocha", "--accent", "follow", "--popup-opacity", "0.8",
                      "--panel-opacity", "0.7", "--floating-panel", "--docked-panel-opacity", "1",
                      "--dock-like-panel", "--flatpak", "--apply")
        self.assertEqual(self.themes(), sorted(f"gattuccino-{f}-{a}" for f in ("latte", "mocha")
                                               for a in palette.SETTINGS_ACCENTS.values()))
        self.assertIn(palette.color("latte", "mauve"),
                      home.read(f"{home.themes}/gattuccino-latte-mauve/gnome-shell/gnome-shell.css"))
        css = home.read(f"{home.themes}/gattuccino-mocha-mauve/gnome-shell/gnome-shell.css")
        self.assertIn(palette.color("mocha", "mauve"), css)
        self.assertIn("#panel.floating-panel", css)
        self.assertIn("#panel.docked-panel", css)
        self.assertIn("#dashtodockContainer #dash .dash-background", css)
        self.assertIn("rgba(30, 30, 46, 0.8)", css)
        self.assertNotIn("st-accent", css)
        self.assertIn(SHELL_VERSION, home.read(f"{home.themes}/gattuccino-mocha-mauve/{shell_theme.MARKER}"))
        self.assertEqual(home.settings(USER_THEME, "name"), "gattuccino-mocha-teal")

        for folder in ("gtk-4.0", "gtk-3.0"):
            self.assertIn('@import url("gattuccino-mocha.css");', home.read(f"{home.config}/{folder}/gtk.css"))
            self.assertTrue(os.path.exists(f"{home.config}/{folder}/gattuccino-latte.css"))
        gtk4 = home.read(f"{home.config}/gtk-4.0/gattuccino-mocha.css")
        self.assertTrue(gtk4.startswith("/* gattuccino:"))
        self.assertIn(f"--window-bg-color: {palette.color('mocha', 'base')};", gtk4)
        self.assertIn("--accent-purple:", gtk4)     # picker swatches
        self.assertIn(palette.color("mocha", "teal"), home.read(f"{home.config}/gtk-4.0/gattuccino-accent.css"))
        self.assertIn("flavor=mocha, accent=follow", home.read(f"{home.config}/gtk-3.0/gattuccino-accent.css"))
        self.assertEqual(home.read(f"{home.config}/gtk-4.0/gtk.css.before-gattuccino"), "/* mine */\n")
        self.assertIn("was kept as gtk.css.before-gattuccino", out)

        self.assertEqual(home.settings(INTERFACE, "color-scheme"), "prefer-dark")
        self.assertEqual(home.settings(INTERFACE, "gtk-theme"), "adw-gtk3-dark")
        self.assertEqual(home.read(home.flatpak_file).splitlines()[1],
                         "filesystems=~/Games;xdg-config/gtk-4.0:ro;xdg-config/gtk-3.0:ro;")

        for uuid in (FLOATING, ACCENT):
            self.assertTrue(os.path.exists(f"{home.extensions}/{uuid}/extension.js"))
            self.assertIn(uuid, home.settings(SHELL, "enabled-extensions"))   # for the next login
        self.assertIn("Log out and back in", out)

        # --- Applying again after the login changes nothing and asks for nothing ---
        home.login()
        before = home.read(f"{home.themes}/gattuccino-mocha-mauve/gnome-shell/gnome-shell.css")
        out = home.ok("apply")
        self.assertNotIn("Log out", out)
        self.assertNotIn("was kept as", out)
        self.assertEqual(home.read(f"{home.themes}/gattuccino-mocha-mauve/gnome-shell/gnome-shell.css"), before)
        self.assertEqual(home.read(home.flatpak_file).count("xdg-config/gtk-4.0"), 1)
        # the theme is selected again through "no theme", so that GNOME Shell reloads it
        self.assertTrue(home.log().rstrip().endswith(
            "gsettings set org.gnome.shell.extensions.user-theme name ''\n"
            "gsettings set org.gnome.shell.extensions.user-theme name 'gattuccino-mocha-teal'"), home.log())

        # --- Light style in Settings: Latte; Frappe for the dark style, one fixed accent, no floating bar ---
        home.set_setting(INTERFACE, "color-scheme", "default")
        home.ok("configure", "--flavor", "frappe", "--accent", "peach", "--no-floating-panel",
                "--no-dock-like-panel", "--apply")
        self.assertEqual(self.themes(), ["gattuccino-frappe-peach", "gattuccino-latte-peach"])
        self.assertEqual(home.settings(USER_THEME, "name"), "gattuccino-latte-peach")
        css = home.read(f"{home.themes}/gattuccino-latte-peach/gnome-shell/gnome-shell.css")
        self.assertIn(palette.color("latte", "peach"), css)
        self.assertNotIn("floating-panel", css)
        self.assertNotIn("dashtodockContainer", css)
        self.assertIn(palette.color("frappe", "peach"),
                      home.read(f"{home.themes}/gattuccino-frappe-peach/gnome-shell/gnome-shell.css"))
        self.assertEqual(sorted(os.listdir(f"{home.config}/gtk-4.0")),
                         ["gattuccino-accent.css", "gattuccino-frappe.css", "gattuccino-latte.css",
                          "gtk.css", "gtk.css.before-gattuccino"])   # Mocha's colors are gone
        self.assertIn('@import url("gattuccino-latte.css");', home.read(f"{home.config}/gtk-4.0/gtk.css"))
        gtk4 = home.read(f"{home.config}/gtk-4.0/gattuccino-latte.css")
        self.assertIn(f"--window-bg-color: {palette.color('latte', 'base')};", gtk4)
        self.assertNotIn("--accent-purple:", gtk4)  # the picker does nothing now: its swatches are left alone
        accent = home.read(f"{home.config}/gtk-3.0/gattuccino-accent.css")
        self.assertIn(palette.color("latte", "peach"), accent)
        self.assertIn("accent=peach", accent)        # for the extension, when the style changes
        self.assertEqual(home.settings(INTERFACE, "gtk-theme"), "adw-gtk3")
        self.assertNotIn("color-scheme", home.log())  # the style is the user's to pick
        self.assertFalse(os.path.exists(f"{home.extensions}/{FLOATING}"))
        self.assertNotIn(FLOATING, home.settings(SHELL, "enabled-extensions"))
        self.assertTrue(os.path.exists(f"{home.extensions}/{ACCENT}"))   # it follows the style

        # --- Without the shell theme: the theme selected before comes back ---
        home.ok("configure", "--no-shell-theme", "--apply")
        self.assertEqual(self.themes(), [])
        self.assertEqual(home.settings(USER_THEME, "name"), "Yaru")
        self.assertTrue(os.path.exists(f"{home.config}/gtk-4.0/gtk.css"))

        # --- Uninstall puts everything back ---
        home.ok("configure", "--shell-theme", "--accent", "follow", "--floating-panel", "--apply")
        home.ok("uninstall")
        self.assertEqual(self.themes(), [])
        self.assertEqual(home.settings(USER_THEME, "name"), "Yaru")
        self.assertEqual(home.read(f"{home.config}/gtk-4.0/gtk.css"), "/* mine */\n")
        self.assertEqual(sorted(os.listdir(f"{home.config}/gtk-4.0")), ["gtk.css"])
        self.assertEqual(os.listdir(f"{home.config}/gtk-3.0"), [])
        self.assertEqual(home.settings(INTERFACE, "color-scheme"), "default")
        self.assertEqual(home.settings(INTERFACE, "gtk-theme"), "Adwaita")
        self.assertEqual(home.read(home.flatpak_file), "[Context]\nfilesystems=~/Games;\n\n[Environment]\nFOO=bar\n")
        self.assertEqual(os.listdir(home.extensions), [USER_THEME_UUID])
        self.assertEqual(home.settings(SHELL, "enabled-extensions"), [USER_THEME_UUID])
        self.assertFalse(os.path.exists(f"{home.config}/gattuccino/state.json"))
        self.assertTrue(os.path.exists(f"{home.config}/gattuccino/preferences.ini"))

    def test_extensions_known_to_the_shell_are_enabled_at_once(self):
        home = self.home
        home.ok("configure", "--floating-panel", "--apply")
        home.login()
        home.ok("configure", "--no-floating-panel", "--apply")
        home.ok("configure", "--floating-panel", "--apply")
        self.assertIn(FLOATING, home.settings(SHELL, "enabled-extensions"))

    def test_a_folder_that_is_not_ours_is_never_overwritten(self):
        home = self.home
        os.makedirs(f"{home.themes}/gattuccino-mocha-teal/gnome-shell")
        result = home.run("apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not created by gattuccino", result.stderr)
        self.assertEqual(self.themes(), ["gattuccino-mocha-teal"])
        self.assertFalse(os.path.exists(f"{home.config}/gtk-4.0"))
        self.assertEqual(home.settings(INTERFACE, "color-scheme"), "default")

    def test_migrates_what_an_earlier_version_left_behind_under_the_old_name(self):
        home = self.home
        legacy_floating, legacy_accent = "floating-panel@gnome-catppuccin", "catppuccin-accent@gnome-catppuccin"

        # The old config folder, with preferences and state from before the rename
        os.makedirs(f"{home.config}/gnome-catppuccin")
        with open(f"{home.config}/gnome-catppuccin/preferences.ini", "w") as f:
            f.write("[preferences]\naccent = peach\n")
        with open(f"{home.config}/gnome-catppuccin/state.json", "w") as f:
            f.write('{"previous": {}, "flatpak": []}\n')

        # An old-named theme folder, marked as this project's own under its old name
        old_theme = f"{home.themes}/gnome-catppuccin-mocha-teal"
        os.makedirs(f"{old_theme}/gnome-shell")
        open(f"{old_theme}/gnome-shell/gnome-shell.css", "w").close()
        open(f"{old_theme}/.gnome-catppuccin", "w").close()

        # Old-named, old-marked application color files
        os.makedirs(f"{home.config}/gtk-4.0")
        with open(f"{home.config}/gtk-4.0/gtk.css", "w") as f:
            f.write("/* gnome-catppuccin: style (light=latte, dark=mocha)\n * anything */\n")
        with open(f"{home.config}/gtk-4.0/gnome-catppuccin-mocha.css", "w") as f:
            f.write("/* gnome-catppuccin: anything */\n")

        # The old extensions, already installed and enabled
        for uuid in (legacy_floating, legacy_accent):
            os.makedirs(f"{home.extensions}/{uuid}")
            open(f"{home.extensions}/{uuid}/extension.js", "w").close()
        home.set_known_extensions([USER_THEME_UUID, legacy_floating, legacy_accent])
        home.set_setting(SHELL, "enabled-extensions", [USER_THEME_UUID, legacy_floating, legacy_accent])

        home.ok("apply")

        # Preferences and state moved over, not lost
        self.assertFalse(os.path.exists(f"{home.config}/gnome-catppuccin"))
        self.assertIn("accent = peach", home.read(f"{home.config}/gattuccino/preferences.ini"))

        # The old theme folder is gone, replaced by the new one built from the migrated preference
        self.assertFalse(os.path.exists(old_theme))
        self.assertIn("gattuccino-mocha-peach", self.themes())

        # The old application color file is gone, replaced by the new one; the old gtk.css
        # is recognized as this project's own too, so it is overwritten and not backed up
        self.assertFalse(os.path.exists(f"{home.config}/gtk-4.0/gnome-catppuccin-mocha.css"))
        self.assertTrue(os.path.exists(f"{home.config}/gtk-4.0/gattuccino-mocha.css"))
        self.assertFalse(os.path.exists(f"{home.config}/gtk-4.0/gtk.css.before-gattuccino"))

        # The old extensions are gone; floating-panel is off by default, so only the
        # new accent extension replaces them
        self.assertFalse(os.path.exists(f"{home.extensions}/{legacy_floating}"))
        self.assertFalse(os.path.exists(f"{home.extensions}/{legacy_accent}"))
        self.assertTrue(os.path.exists(f"{home.extensions}/{ACCENT}"))
        enabled = home.settings(SHELL, "enabled-extensions")
        self.assertNotIn(legacy_floating, enabled)
        self.assertNotIn(legacy_accent, enabled)

    def test_without_user_themes_the_themes_are_installed_and_a_note_says_what_is_missing(self):
        home = FakeHome(user_themes="no")
        self.addCleanup(home.close)
        home.seed_sources(SOURCES)
        out = home.ok("apply")
        self.assertEqual(len(os.listdir(home.themes)), 18)
        self.assertIn("User Themes extension is not installed", out)
        self.assertIn("adw-gtk3", out)   # not installed in this home either

    def test_user_themes_packaged_by_the_distribution(self):
        home = FakeHome(user_themes="system")
        self.addCleanup(home.close)
        home.seed_sources(SOURCES)
        home.set_setting(INTERFACE, "color-scheme", "prefer-dark")
        home.ok("configure", "--accent", "blue", "--apply")
        self.assertEqual(home.settings(USER_THEME, "name"), "gattuccino-mocha-blue")

    def test_the_style_picked_in_settings_selects_the_flavor(self):
        home = self.home
        home.ok("configure", "--flavor", "macchiato", "--accent", "follow", "--apply")
        self.assertEqual(home.settings(USER_THEME, "name"), "gattuccino-latte-teal")
        self.assertIn('@import url("gattuccino-latte.css");', home.read(f"{home.config}/gtk-3.0/gtk.css"))
        home.set_setting(INTERFACE, "color-scheme", "prefer-dark")
        home.ok("apply")
        self.assertEqual(home.settings(USER_THEME, "name"), "gattuccino-macchiato-teal")
        self.assertIn('@import url("gattuccino-macchiato.css");', home.read(f"{home.config}/gtk-3.0/gtk.css"))
        self.assertIn(palette.color("macchiato", "teal"), home.read(f"{home.config}/gtk-4.0/gattuccino-accent.css"))

    def test_accent_selection_adds_and_removes_the_selection_rules(self):
        home = self.home
        home.ok("configure", "--accent-selection", "--apply")
        # the dock of Dash to Dock: a stylesheet of its own, loaded by the accent extension
        for flavor in ("latte", "mocha"):
            dock = home.read(f"{home.themes}/gattuccino-{flavor}-teal/gnome-shell/{shell_theme.DOCK_STYLESHEET}")
            self.assertEqual(dock, shell_theme.dock_accent_css(flavor, "teal"))
            self.assertIn(palette.color(flavor, "teal"), dock)
        for folder, rule in (("gtk-4.0", ".navigation-sidebar row:selected,"), ("gtk-3.0", "menu menuitem:hover,")):
            selection = home.read(f"{home.config}/{folder}/gattuccino-selection.css")
            self.assertIn(rule, selection)
            # the flavor files pull it in, not gtk.css: the accent extension rewrites that one
            for flavor in ("latte", "mocha"):
                self.assertIn('@import url("gattuccino-selection.css");',
                              home.read(f"{home.config}/{folder}/gattuccino-{flavor}.css"))
            self.assertNotIn("selection", home.read(f"{home.config}/{folder}/gtk.css"))

        home.ok("configure", "--no-accent-selection", "--apply")
        for flavor in ("latte", "mocha"):
            self.assertEqual(sorted(os.listdir(f"{home.themes}/gattuccino-{flavor}-teal/gnome-shell")),
                             ["gnome-shell.css"])
        for folder in ("gtk-4.0", "gtk-3.0"):
            self.assertFalse(os.path.exists(f"{home.config}/{folder}/gattuccino-selection.css"))
            self.assertNotIn("selection", home.read(f"{home.config}/{folder}/gattuccino-mocha.css"))

    def test_the_style_set_by_an_earlier_version_is_no_longer_put_back(self):
        home = self.home
        os.makedirs(f"{home.config}/gattuccino")
        with open(f"{home.config}/gattuccino/state.json", "w") as f:
            f.write('{"previous": {"color-scheme": "prefer-light"}, "flatpak": []}\n')
        home.ok("apply")
        home.set_setting(INTERFACE, "color-scheme", "prefer-dark")
        home.ok("uninstall")
        self.assertEqual(home.settings(INTERFACE, "color-scheme"), "prefer-dark")

    def test_an_unsupported_gnome_shell_changes_nothing(self):
        home = FakeHome(shell_version="47.2")
        self.addCleanup(home.close)
        result = home.run("apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("version 48 or later is needed", result.stderr)
        self.assertFalse(os.path.exists(home.themes))
        self.assertFalse(os.path.exists(f"{home.config}/gtk-4.0"))

    def test_application_colors_alone_need_no_gnome_shell_sources(self):
        home = FakeHome(shell_version="47.2")   # no sources seeded, and none could be built
        self.addCleanup(home.close)
        home.ok("configure", "--no-shell-theme", "--flavor", "frappe", "--accent", "sky", "--apply")
        self.assertIn(palette.color("latte", "sky"), home.read(f"{home.config}/gtk-4.0/gattuccino-accent.css"))
        self.assertTrue(os.path.exists(f"{home.config}/gtk-4.0/gattuccino-frappe.css"))
        self.assertFalse(os.path.exists(home.themes))

    def test_build_writes_to_a_folder_and_changes_nothing(self):
        home = self.home
        home.ok("configure", "--accent", "green", "--flavor", "macchiato")
        output = f"{home.root}/out"
        home.ok("build", "--output", output)
        self.assertEqual(sorted(os.listdir(f"{output}/themes")),
                         ["gattuccino-latte-green", "gattuccino-macchiato-green"])
        self.assertTrue(os.path.exists(f"{output}/gtk-4.0/gtk.css"))
        self.assertTrue(os.path.exists(f"{output}/gtk-3.0/gattuccino-accent.css"))
        self.assertFalse(os.path.exists(home.themes))
        self.assertEqual(home.log(), "")

    def test_configure_asks_only_in_a_terminal(self):
        result = self.home.run("configure", input="latte\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing to change", result.stderr)
        self.assertFalse(os.path.exists(f"{self.home.config}/gattuccino/preferences.ini"))


if __name__ == "__main__":
    unittest.main()
