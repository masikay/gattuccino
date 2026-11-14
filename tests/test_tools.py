"""The tools in a terminal, themed in step with the flavor and the accent, run for real in a throwaway home."""

import json
import os
import unittest

from gattuccino import palette, preferences as prefs, tools
from gattuccino.desktop import Desktop
from gattuccino.tools import btop, eza, fzf, ghostty, ptyxis

from .support import FakeHome

INTERFACE = "org.gnome.desktop.interface"
ACCENT_SCHEMA = "org.gnome.shell.extensions.gattuccino-accent"
COMMANDS = ("gsettings", "gnome-extensions", "flatpak", "gnome-shell", "glib-compile-schemas", "eza", "fzf", "btop", "ghostty", "ptyxis", "gdbus", "systemctl")


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

    def test_every_flavor_has_the_official_theme_of_btop(self):
        for flavor in (palette.LIGHT_FLAVOR, *palette.DARK_FLAVORS):
            self.assertTrue(os.path.isfile(btop.theme_file(flavor)), flavor)

    def test_every_flavor_has_the_colors_of_the_official_port_for_ptyxis_to_take(self):
        for flavor in (palette.LIGHT_FLAVOR, *palette.DARK_FLAVORS):
            colors = ptyxis.colors(flavor)
            self.assertEqual(sorted(k for k in colors if k.startswith("color")), sorted(f"color{n}" for n in range(16)))
            self.assertTrue({"background", "foreground", "cursor-color", "cursor-text"} <= set(colors), flavor)

    def test_every_flavor_has_the_official_theme_of_ghostty(self):
        for flavor in (palette.LIGHT_FLAVOR, *palette.DARK_FLAVORS):
            self.assertTrue(os.path.isfile(ghostty.theme_file(flavor)), flavor)

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


class BtopTest(unittest.TestCase):
    CONF = (
        '#? Config file for btop v.1.4.7\n\n#* Name of a theme\n'
        'color_theme = "/home/u/.config/btop/themes/catppuccin_mocha.theme"\n\ntheme_background = true\n'
        'truecolor = true\n')

    def setUp(self):
        self.home = FakeHome(commands=COMMANDS)
        self.addCleanup(self.home.close)
        self.theme = f"{self.home.config}/btop/themes/gattuccino.theme"
        self.conf = f"{self.home.config}/btop/btop.conf"

    def configure(self, *args):
        return self.home.ok("configure", "--no-shell-theme", "--no-gtk-theme", *args)

    def put_conf(self, text):
        os.makedirs(os.path.dirname(self.conf), exist_ok=True)
        with open(self.conf, "w") as f:
            f.write(text)

    def test_the_accent_is_the_highlighted_keys_and_the_selected_line_and_all_the_rest_is_the_official_port(self):
        theme = read(btop.theme_file("mocha"))
        changed = btop.with_accent(theme, palette.color("mocha", "teal"))
        self.assertIn('theme[hi_fg]="#94e2d5"', changed)
        self.assertIn('theme[selected_fg]="#94e2d5"', changed)
        before = [line for line in theme.splitlines() if "hi_fg" not in line and "selected_fg" not in line]
        after = [line for line in changed.splitlines() if "hi_fg" not in line and "selected_fg" not in line]
        self.assertEqual(before, after)

    def test_it_writes_the_theme_and_makes_a_btop_conf_that_asks_for_it_when_there_is_none(self):
        # the light style is Latte, and the accent picked in Settings is teal
        self.configure("--tool-btop")
        text = self.home.read(self.theme)
        self.assertTrue(text.startswith("# gattuccino: btop theme (flavor=latte, accent=teal)\n"))
        self.assertIn(f'theme[hi_fg]="{palette.color("latte", "teal")}"', text)
        self.assertIn('theme[main_bg]="#eff1f5"', text)                    # the flavor's own colors
        self.assertEqual(self.home.read(self.conf), 'color_theme = "gattuccino"\n')

        self.configure("--no-tool-btop")                                   # a file that was only this line
        self.assertFalse(os.path.exists(self.theme))
        self.assertFalse(os.path.exists(self.conf))

    def test_only_the_color_theme_line_of_a_btop_conf_is_touched_and_it_is_put_back(self):
        self.put_conf(self.CONF)
        out = self.configure("--tool-btop")
        self.assertIn('btop.conf had color_theme = "/home/u/.config/btop/themes/catppuccin_mocha.theme"', out)
        self.assertEqual(self.home.read(self.conf), self.CONF.replace(
            '"/home/u/.config/btop/themes/catppuccin_mocha.theme"', '"gattuccino"'))

        # btop writes its file back with a setting changed: the theme is still asked for, and still put back
        self.put_conf(self.home.read(self.conf).replace("truecolor = true", "truecolor = false"))
        self.home.ok("sync")
        self.configure("--no-tool-btop")
        self.assertEqual(self.home.read(self.conf), self.CONF.replace("truecolor = true", "truecolor = false"))
        self.assertFalse(os.path.exists(self.theme))

    def test_a_btop_conf_without_the_line_gets_it_and_loses_it(self):
        self.put_conf("theme_background = true\n")
        self.configure("--tool-btop")
        self.assertEqual(self.home.read(self.conf), 'theme_background = true\ncolor_theme = "gattuccino"\n')
        self.configure("--no-tool-btop")
        self.assertEqual(self.home.read(self.conf), "theme_background = true\n")

    def test_it_follows_the_style_and_the_accent_and_leaves_btop_conf_alone_once_it_asks_for_the_theme(self):
        self.put_conf(self.CONF)
        self.configure("--tool-btop", "--flavor", "macchiato")
        asked = self.home.read(self.conf)
        self.home.set_setting(INTERFACE, "color-scheme", "prefer-dark")
        self.home.set_setting(INTERFACE, "accent-color", "pink")
        self.home.ok("sync")
        self.assertIn("flavor=macchiato, accent=pink", self.home.read(self.theme))
        self.assertIn('theme[main_bg]="#24273a"', self.home.read(self.theme))
        self.assertEqual(self.home.read(self.conf), asked)

    def test_a_btop_conf_that_is_a_symlink_is_never_written_through(self):
        repository = f"{self.home.home}/dotfiles"
        os.makedirs(repository)
        with open(f"{repository}/btop.conf", "w") as f:
            f.write(self.CONF)
        os.makedirs(os.path.dirname(self.conf))
        os.symlink(f"{repository}/btop.conf", self.conf)

        out = self.configure("--tool-btop")
        self.assertIn("is a symlink, so it is not edited", out)
        self.assertIn('color_theme = "gattuccino"', out)                   # what to put in it
        self.assertEqual(self.home.read(f"{repository}/btop.conf"), self.CONF)
        self.assertTrue(os.path.islink(self.conf))
        self.assertTrue(os.path.exists(self.theme))                        # the theme is there for it

        self.configure("--no-tool-btop")
        self.assertEqual(self.home.read(f"{repository}/btop.conf"), self.CONF)
        self.assertFalse(os.path.exists(self.theme))

    def test_uninstall_puts_the_color_theme_back(self):
        self.put_conf(self.CONF)
        self.configure("--tool-btop")
        self.home.ok("uninstall")
        self.assertEqual(self.home.read(self.conf), self.CONF)
        self.assertFalse(os.path.exists(self.theme))


class GhosttyTest(unittest.TestCase):
    CONFIG = "theme = catppuccin-mocha.conf\nbackground-opacity = 0.9\nwindow-width = 120\n"

    def setUp(self):
        self.home = FakeHome(commands=COMMANDS)
        self.addCleanup(self.home.close)
        self.folder = f"{self.home.config}/ghostty"
        self.config = f"{self.folder}/config.ghostty"
        self.include = f"{self.folder}/gattuccino"
        self.light, self.dark = f"{self.folder}/themes/gattuccino-light", f"{self.folder}/themes/gattuccino-dark"

    def configure(self, *args):
        return self.home.ok("configure", "--no-shell-theme", "--no-gtk-theme", *args)

    def put_config(self, text):
        os.makedirs(self.folder, exist_ok=True)
        with open(self.config, "w") as f:
            f.write(text)

    def test_only_the_cursor_takes_the_accent_and_all_the_rest_is_the_official_port(self):
        theme = read(ghostty.theme_file("mocha"))
        changed = ghostty.with_accent(theme, palette.color("mocha", "teal"))
        self.assertIn("cursor-color = 94e2d5", changed)
        words = lambda text: [line for line in text.splitlines() if not line.startswith("cursor-color")]  # noqa: E731
        self.assertEqual(words(theme), words(changed))

    def test_both_styles_are_written_at_once_for_ghostty_to_follow_the_desktop_by_itself(self):
        # Latte for the light style, the dark flavor chosen for the dark one; the accent picked in Settings is teal
        self.configure("--tool-ghostty", "--flavor", "frappe")
        light, dark = self.home.read(self.light), self.home.read(self.dark)
        self.assertTrue(light.startswith("# gattuccino: ghostty theme, light (flavor=latte, accent=teal)\n"))
        self.assertTrue(dark.startswith("# gattuccino: ghostty theme, dark (flavor=frappe, accent=teal)\n"))
        self.assertTrue(light.endswith(ghostty.with_accent(read(ghostty.theme_file("latte")),
                                                           palette.color("latte", "teal"))))
        self.assertTrue(dark.endswith(ghostty.with_accent(read(ghostty.theme_file("frappe")),
                                                          palette.color("frappe", "teal"))))
        self.assertIn("theme = light:gattuccino-light,dark:gattuccino-dark\n", self.home.read(self.include))

    def test_a_configuration_is_made_when_there_is_none_and_taken_away_again(self):
        self.configure("--tool-ghostty")
        self.assertEqual(self.home.read(self.config).splitlines()[1], "config-file = ?gattuccino")
        self.configure("--no-tool-ghostty")
        for path in (self.config, self.include, self.light, self.dark):
            self.assertFalse(os.path.exists(path), path)

    def test_one_line_is_added_to_a_configuration_of_ones_own_and_only_that_is_taken_away(self):
        self.put_config(self.CONFIG)
        out = self.configure("--tool-ghostty")
        self.assertIn("Your own `theme` in the configuration of Ghostty stays", out)
        text = self.home.read(self.config)
        self.assertTrue(text.startswith(self.CONFIG))                       # all of it is as it was
        self.assertTrue(text.endswith("config-file = ?gattuccino\n"))

        before = text
        self.home.ok("sync")                                                # once, not every time
        self.assertEqual(self.home.read(self.config), before)

        self.configure("--no-tool-ghostty")
        self.assertEqual(self.home.read(self.config), self.CONFIG)

    def test_the_style_changes_nothing_but_the_accent_changes_the_cursor(self):
        self.configure("--tool-ghostty")
        before = (self.home.read(self.light), self.home.read(self.dark))
        self.home.set_setting(INTERFACE, "color-scheme", "prefer-dark")
        self.home.ok("sync")                                                # Ghostty follows the desktop itself
        self.assertEqual((self.home.read(self.light), self.home.read(self.dark)), before)

        self.home.set_setting(INTERFACE, "accent-color", "pink")
        self.home.ok("sync")
        self.assertIn(f"cursor-color = {palette.color('latte', 'pink').lstrip('#')}", self.home.read(self.light))
        self.assertIn(f"cursor-color = {palette.color('mocha', 'pink').lstrip('#')}", self.home.read(self.dark))

    def test_a_configuration_that_is_a_symlink_is_never_written_through(self):
        repository = f"{self.home.home}/dotfiles"
        os.makedirs(repository)
        with open(f"{repository}/config.ghostty", "w") as f:
            f.write(self.CONFIG)
        os.makedirs(self.folder)
        os.symlink(f"{repository}/config.ghostty", self.config)

        out = self.configure("--tool-ghostty")
        self.assertIn("is a symlink, so it is not edited", out)
        self.assertIn("config-file = ?gattuccino", out)                     # what to put in it
        self.assertEqual(self.home.read(f"{repository}/config.ghostty"), self.CONFIG)
        self.assertTrue(os.path.exists(self.light))

    def test_a_ghostty_that_is_running_is_asked_to_read_its_configuration_again_and_one_that_is_not_is_left_alone(self):
        # asking one that is not there starts it, with no window: it is looked for first
        self.configure("--tool-ghostty")
        log = self.home.log()
        self.assertIn("NameHasOwner", log)
        self.assertNotIn("reload-config", log)

        self.home.env["FAKE_GHOSTTY_RUNNING"] = "1"
        self.home.ok("sync")                                                # nothing has changed: no call
        self.assertNotIn("reload-config", self.home.log())
        self.home.set_setting(INTERFACE, "accent-color", "pink")
        self.home.ok("sync")
        self.assertIn("org.gtk.Actions.Activate reload-config", self.home.log())

    def test_uninstall_puts_everything_back(self):
        self.put_config(self.CONFIG)
        self.configure("--tool-ghostty")
        self.home.ok("uninstall")
        self.assertEqual(self.home.read(self.config), self.CONFIG)
        for path in (self.include, self.light, self.dark):
            self.assertFalse(os.path.exists(path), path)


class PtyxisTest(unittest.TestCase):
    SCHEMA = "org.gnome.Ptyxis"
    PROFILES = ("aaaa1111", "bbbb2222")

    def setUp(self):
        self.home = FakeHome(commands=COMMANDS)
        self.addCleanup(self.home.close)
        self.palette = f"{self.home.data}/org.gnome.Ptyxis/palettes/Gattuccino.palette"
        # two profiles, with palettes of their own, as Ptyxis keeps them
        store = json.loads(self.home.read(self.home._files["gsettings.json"]))
        store[self.SCHEMA] = {"profile-uuids": list(self.PROFILES), "interface-style": "system"}
        store[self.profile("aaaa1111")] = {"palette": "Catppuccin Mocha"}
        store[self.profile("bbbb2222")] = {"palette": "Linux"}
        self.home.write_settings(store)

    def profile(self, uuid):
        return f"org.gnome.Ptyxis.Profile:/org/gnome/Ptyxis/Profiles/{uuid}/"

    def palettes(self):
        return [self.home.settings(self.profile(uuid), "palette") for uuid in self.PROFILES]

    def configure(self, *args):
        return self.home.ok("configure", "--no-shell-theme", "--no-gtk-theme", *args)

    def test_the_palette_has_latte_for_light_and_the_dark_flavor_for_dark_and_the_accent_for_the_cursor(self):
        self.configure("--tool-ptyxis", "--flavor", "macchiato")
        text = self.home.read(self.palette)
        self.assertTrue(text.startswith("# gattuccino: ptyxis palette (flavor=latte and macchiato, accent=teal)\n"))

        try:   # as Ptyxis reads it
            from gi.repository import GLib
        except ImportError:
            GLib = None
        if GLib is not None:
            keys = GLib.KeyFile()
            keys.load_from_data(text, len(text), GLib.KeyFileFlags.NONE)
            self.assertEqual(keys.get_string("Palette", "Name"), "Gattuccino")
            for section, flavor in (("Light", "latte"), ("Dark", "macchiato")):
                required = ["Foreground", "Background", *[f"Color{n}" for n in range(16)]]
                for key in required:
                    self.assertTrue(keys.get_string(section, key).startswith("#"), (section, key))
                self.assertEqual(keys.get_string(section, "Cursor"), palette.color(flavor, "teal").lower())
                self.assertEqual(keys.get_string(section, "Background"), palette.color(flavor, "base").lower())
                self.assertEqual(keys.get_string(section, "Color1"), palette.color(flavor, "red").lower())

    def test_the_profiles_are_pointed_at_it_and_get_back_what_they_had(self):
        self.configure("--tool-ptyxis")
        self.assertEqual(self.palettes(), ["Gattuccino", "Gattuccino"])
        self.home.ok("sync")                                                # again: what they had is not lost
        self.configure("--no-tool-ptyxis")
        self.assertEqual(self.palettes(), ["Catppuccin Mocha", "Linux"])
        self.assertFalse(os.path.exists(self.palette))

    def test_a_profile_that_was_changed_to_another_palette_since_is_left_alone_when_it_is_turned_off(self):
        self.configure("--tool-ptyxis")
        self.home.set_setting(self.profile("bbbb2222"), "palette", "Nord")   # chosen by hand
        self.configure("--no-tool-ptyxis")
        self.assertEqual(self.palettes(), ["Catppuccin Mocha", "Nord"])

    def test_it_follows_the_accent(self):
        self.configure("--tool-ptyxis")
        self.home.set_setting(INTERFACE, "accent-color", "pink")
        self.home.ok("sync")
        self.assertIn(f"Cursor={palette.color('latte', 'pink').lower()}", self.home.read(self.palette))
        self.assertIn(f"Cursor={palette.color('mocha', 'pink').lower()}", self.home.read(self.palette))

    def test_it_says_when_ptyxis_is_kept_in_one_style(self):
        self.home.set_setting(self.SCHEMA, "interface-style", "dark")
        out = self.configure("--tool-ptyxis")
        self.assertIn("Ptyxis is set to stay dark", out)
        self.assertIn("interface-style system", out)
        self.home.set_setting(self.SCHEMA, "interface-style", "system")
        self.assertNotIn("Ptyxis is set to stay", self.configure("--tool-ptyxis"))

    def test_uninstall_puts_everything_back(self):
        self.configure("--tool-ptyxis")
        self.home.ok("uninstall")
        self.assertEqual(self.palettes(), ["Catppuccin Mocha", "Linux"])
        self.assertFalse(os.path.exists(self.palette))

    def test_a_ptyxis_with_no_profiles_is_only_given_the_palette(self):
        store = json.loads(self.home.read(self.home._files["gsettings.json"]))
        del store[self.SCHEMA]
        self.home.write_settings(store)
        self.configure("--tool-ptyxis")
        self.assertTrue(os.path.exists(self.palette))
