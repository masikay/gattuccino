"""The tools in a terminal, themed in step with the flavor and the accent, run for real in a throwaway home."""

import os
import unittest

from gattuccino import palette, preferences as prefs, tools
from gattuccino.desktop import Desktop
from gattuccino.tools import eza

from .support import FakeHome

INTERFACE = "org.gnome.desktop.interface"
ACCENT_SCHEMA = "org.gnome.shell.extensions.gattuccino-accent"
COMMANDS = ("gsettings", "gnome-extensions", "flatpak", "gnome-shell", "glib-compile-schemas", "eza")


def official(flavor, accent):
    with open(eza.theme_file(flavor, accent), encoding="utf-8") as f:
        return f.read()


class RegistryTest(unittest.TestCase):
    def test_every_tool_is_a_preference_with_the_words_of_the_tool(self):
        for tool in tools.all_tools():
            self.assertIn(tool.preference, prefs.SPECS)
            self.assertEqual(prefs.SPECS[tool.preference].help, tool.help)
        group = dict(prefs.GROUPS)["Tools"]
        self.assertEqual(sorted(group), sorted(tools.preference_names()))

    def test_every_flavor_and_accent_has_the_official_theme_of_eza(self):
        for flavor in (palette.LIGHT_FLAVOR, *palette.DARK_FLAVORS):
            for accent in palette.ACCENTS:
                self.assertTrue(os.path.isfile(eza.theme_file(flavor, accent)), (flavor, accent))

    def test_a_tool_that_is_not_there_is_not_asked_about(self):
        desktop = Desktop(environment={"HOME": "/nonexistent", "PATH": "/nonexistent"})
        self.assertFalse(tools.installed("tool_eza", desktop))
        self.assertTrue(tools.installed("flavor", desktop))   # anything that is not a tool


class EzaTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome(commands=COMMANDS)
        self.addCleanup(self.home.close)
        self.theme = f"{self.home.config}/eza/theme.yml"

    def configure(self, *args):
        return self.home.ok("configure", "--no-shell-theme", "--no-gtk-theme", *args)

    def test_it_is_themed_with_the_official_theme_of_the_flavor_and_accent_in_use(self):
        # the light style is Latte, and the accent picked in Settings is teal
        self.configure("--tool-eza")
        text = self.home.read(self.theme)
        first, rest = text.split("\n", 1)
        self.assertEqual(first, "# gattuccino: eza theme (flavor=latte, accent=teal)")
        self.assertTrue(text.endswith(official("latte", "teal")))          # the official file, unchanged

    def test_it_follows_the_style_and_the_accent_as_they_are_changed_in_settings(self):
        self.configure("--tool-eza", "--flavor", "frappe")
        self.home.set_setting(INTERFACE, "color-scheme", "prefer-dark")
        self.home.set_setting(INTERFACE, "accent-color", "pink")
        self.home.ok("sync")                                               # what the extension runs
        text = self.home.read(self.theme)
        self.assertTrue(text.startswith("# gattuccino: eza theme (flavor=frappe, accent=pink)"))
        self.assertTrue(text.endswith(official("frappe", "pink")))

        self.home.set_setting(INTERFACE, "color-scheme", "default")
        self.home.ok("sync")
        self.assertIn("flavor=latte, accent=pink", self.home.read(self.theme))

    # eza gives LS_COLORS priority over its theme, kind by kind: folders stay blue
    def test_it_says_when_ls_colors_is_set_in_the_shell_and_what_that_does_to_the_theme(self):
        self.home.env["LS_COLORS"] = "rs=0:di=01;34:ln=01;36:ex=01;32:*.tar=01;31"
        out = self.configure("--tool-eza")
        self.assertIn("LS_COLORS is set in your shell", out)
        self.assertIn("folders, symlinks, executables", out)
        self.assertIn("`LS_COLORS= eza`", out)
        self.assertTrue(os.path.exists(self.theme))                        # the theme is written all the same

    def test_it_says_nothing_when_ls_colors_has_nothing_to_say_about_what_the_theme_colors(self):
        self.home.env["LS_COLORS"] = "rs=0:*.tar=01;31"
        self.assertNotIn("LS_COLORS", self.configure("--tool-eza"))
        del self.home.env["LS_COLORS"]
        self.assertNotIn("LS_COLORS", self.configure("--tool-eza"))

    def test_a_fixed_accent_stays(self):
        self.configure("--tool-eza", "--accent", "peach")
        self.home.set_setting(INTERFACE, "accent-color", "blue")
        self.home.ok("sync")
        self.assertIn("accent=peach", self.home.read(self.theme))

    def test_a_theme_of_ones_own_is_kept_and_put_back(self):
        os.makedirs(os.path.dirname(self.theme))
        with open(self.theme, "w") as f:
            f.write("colourful: false\n")
        out = self.configure("--tool-eza")
        self.assertIn("kept as theme.yml.before-gattuccino", out)
        self.assertEqual(self.home.read(self.theme + ".before-gattuccino"), "colourful: false\n")

        self.configure("--no-tool-eza")
        self.assertEqual(self.home.read(self.theme), "colourful: false\n")
        self.assertFalse(os.path.exists(self.theme + ".before-gattuccino"))

    def test_a_symlink_into_a_dotfiles_repository_is_moved_aside_and_never_written_through(self):
        repository = f"{self.home.home}/dotfiles"
        os.makedirs(repository)
        target = f"{repository}/theme.yml"
        with open(target, "w") as f:
            f.write("colourful: false\n")
        os.makedirs(os.path.dirname(self.theme))
        os.symlink(target, self.theme)

        self.configure("--tool-eza")
        self.assertFalse(os.path.islink(self.theme))                       # a file of ours now
        self.assertEqual(self.home.read(target), "colourful: false\n")    # the repository untouched
        self.assertTrue(os.path.islink(self.theme + ".before-gattuccino"))

        self.home.ok("sync")                                               # and again: still untouched
        self.assertEqual(self.home.read(target), "colourful: false\n")

        self.configure("--no-tool-eza")
        self.assertTrue(os.path.islink(self.theme))                        # the link is back, as it was
        self.assertEqual(os.readlink(self.theme), target)

    def test_turning_it_off_and_uninstall_take_it_away_and_leave_the_file_of_a_person_alone(self):
        self.configure("--tool-eza")
        self.assertTrue(os.path.exists(self.theme))
        self.configure("--no-tool-eza")
        self.assertFalse(os.path.exists(self.theme))

        # a file that is not ours is never removed, not by being off, not by uninstall
        with open(self.theme, "w") as f:
            f.write("colourful: false\n")
        self.configure("--no-tool-eza")
        self.home.ok("uninstall")
        self.assertEqual(self.home.read(self.theme), "colourful: false\n")

        self.configure("--tool-eza")
        self.home.ok("uninstall")
        self.assertEqual(self.home.read(self.theme), "colourful: false\n")   # its own, put back

    def test_the_extension_is_told_what_to_run_only_while_a_tool_is_wanted(self):
        self.home.ok("configure", "--no-shell-theme", "--tool-eza", "--apply")
        command = self.home.settings(ACCENT_SCHEMA, "sync-command")
        self.assertTrue(command.endswith("/gattuccino"), command)
        self.assertTrue(os.path.isfile(command))

        self.home.ok("configure", "--no-tool-eza")
        self.assertEqual(self.home.settings(ACCENT_SCHEMA, "sync-command"), "")

    def test_nothing_is_written_for_a_tool_that_is_not_wanted(self):
        self.configure("--flavor", "frappe")
        self.home.ok("sync")
        self.assertFalse(os.path.exists(self.theme))
