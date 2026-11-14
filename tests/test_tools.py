"""The tools in a terminal, themed in step with the flavor and the accent, run for real in a throwaway home."""

import os
import unittest

from gattuccino import palette, preferences as prefs, tools
from gattuccino.desktop import Desktop
from gattuccino.tools import eza, fzf

from .support import FakeHome

INTERFACE = "org.gnome.desktop.interface"
ACCENT_SCHEMA = "org.gnome.shell.extensions.gattuccino-accent"
COMMANDS = ("gsettings", "gnome-extensions", "flatpak", "gnome-shell", "glib-compile-schemas", "eza", "fzf", "systemctl")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def official(flavor, accent):
    return read(eza.theme_file(flavor, accent))


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

    def test_every_flavor_has_the_official_theme_of_fzf(self):
        for flavor in (palette.LIGHT_FLAVOR, *palette.DARK_FLAVORS):
            self.assertTrue(os.path.isfile(fzf.theme_file(flavor)), flavor)

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


class FzfTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome(commands=COMMANDS)
        self.addCleanup(self.home.close)
        self.options = f"{self.home.config}/fzf/gattuccino.rc"
        self.environment = f"{self.home.config}/environment.d/60-gattuccino-fzf.conf"
        # what a person's shell has, which the notes are about
        for name in ("FZF_DEFAULT_OPTS", "FZF_DEFAULT_OPTS_FILE"):
            self.home.env.pop(name, None)

    def configure(self, *args):
        return self.home.ok("configure", "--no-shell-theme", "--no-gtk-theme", *args)

    def test_the_accent_is_the_prompt_and_the_pointer_and_all_the_rest_is_the_official_port(self):
        theme = read(fzf.theme_file("mocha"))
        changed = fzf.with_accent(theme, palette.color("mocha", "teal"))
        self.assertEqual(changed.count("#94E2D5"), 2)
        self.assertIn("pointer:#94E2D5", changed)
        self.assertIn("prompt:#94E2D5", changed)
        # nothing else is touched: the same words, but for the two colors
        words = lambda text: sorted(w for w in text.split() if "pointer" not in w and "prompt" not in w)  # noqa: E731
        self.assertEqual(words(theme), words(changed))

    def test_the_options_file_is_the_official_theme_with_the_accent_and_environment_d_points_at_it(self):
        # the light style is Latte, and the accent picked in Settings is teal
        self.configure("--tool-fzf")
        text = self.home.read(self.options)
        self.assertTrue(text.startswith("# gattuccino: fzf theme (flavor=latte, accent=teal)\n"))
        official = read(fzf.theme_file("latte"))
        self.assertTrue(text.endswith(fzf.with_accent(official, palette.color("latte", "teal"))))

        environment = self.home.read(self.environment)
        self.assertTrue(environment.startswith("# gattuccino: fzf options file"))
        self.assertIn(f"\nFZF_DEFAULT_OPTS_FILE={self.options}\n", environment)

    def test_it_follows_the_style_and_the_accent_as_they_are_changed_in_settings(self):
        self.configure("--tool-fzf", "--flavor", "macchiato")
        self.home.set_setting(INTERFACE, "color-scheme", "prefer-dark")
        self.home.set_setting(INTERFACE, "accent-color", "pink")
        self.home.ok("sync")
        text = self.home.read(self.options)
        self.assertIn("flavor=macchiato, accent=pink", text)
        self.assertIn(f"prompt:{palette.color('macchiato', 'pink').upper()}", text)
        self.assertIn("bg:#24273A", text)                                  # the flavor's own colors

    def test_turning_it_off_takes_both_files_away_and_leaves_the_files_of_a_person_alone(self):
        self.configure("--tool-fzf")
        self.configure("--no-tool-fzf")
        self.assertFalse(os.path.exists(self.options))
        self.assertFalse(os.path.exists(self.environment))

        os.makedirs(os.path.dirname(self.environment), exist_ok=True)
        with open(self.environment, "w") as f:
            f.write("MINE=1\n")
        out = self.configure("--tool-fzf")
        self.assertIn("kept as 60-gattuccino-fzf.conf.before-gattuccino", out)
        self.configure("--no-tool-fzf")
        self.assertEqual(self.home.read(self.environment), "MINE=1\n")

    def test_it_says_to_log_in_again_until_the_variable_is_there(self):
        self.assertIn("log out and back in", self.configure("--tool-fzf"))
        self.home.env["FZF_DEFAULT_OPTS_FILE"] = self.options              # after the login
        self.assertNotIn("log out and back in", self.configure("--tool-fzf"))

    def test_systemd_is_asked_to_read_the_file_again_once_it_is_written_and_once_it_is_gone(self):
        # a user manager that was kept running (logging back in within ten seconds) never saw it
        self.configure("--tool-fzf")
        self.assertEqual(self.home.log().count("systemctl --user daemon-reload"), 1)
        self.configure("--tool-fzf")                                       # as it is: nothing to ask
        self.assertEqual(self.home.log().count("systemctl --user daemon-reload"), 1)
        self.configure("--no-tool-fzf")
        self.assertEqual(self.home.log().count("systemctl --user daemon-reload"), 2)

    def test_it_says_when_the_colors_of_the_shell_win(self):
        self.home.env["FZF_DEFAULT_OPTS"] = "--height=60% --color=bg+:#313244"
        out = self.configure("--tool-fzf")
        self.assertIn("has --color in it", out)
        self.assertTrue(os.path.exists(self.options))                      # written all the same

        self.home.env["FZF_DEFAULT_OPTS"] = "--height=60% --layout=reverse"
        self.assertNotIn("has --color in it", self.configure("--tool-fzf"))

    def test_it_says_when_fzf_is_too_old_to_read_the_file(self):
        self.home.env["FAKE_FZF_VERSION"] = "0.57.0"
        self.assertIn("older than 0.58", self.configure("--tool-fzf"))
        self.home.env["FAKE_FZF_VERSION"] = "0.58.0"
        self.assertNotIn("older than 0.58", self.configure("--tool-fzf"))
