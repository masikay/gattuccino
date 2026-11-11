import os
import re
import tempfile
import unittest

from gattuccino import palette, shell_theme
from gattuccino.shell_theme import ShellOptions

from .support import test_sources

SOURCES = test_sources()
ADWAITA = re.compile("#222226|#36363a|#fafafb|#cd9309|#3584e4", re.I)   # colors of the stylesheet being replaced


def rules(css):
    """{selector: {property: value}} of a compiled stylesheet."""
    result = {}
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
        declarations = dict(d.split(":", 1) for d in match.group(2).split(";") if ":" in d)
        for selector in match.group(1).split(","):
            result.setdefault(" ".join(selector.split()), {}).update(
                {k.strip(): v.strip() for k, v in declarations.items()})
    return result


@unittest.skipUnless(SOURCES, "the GNOME Shell stylesheets could not be downloaded")
@unittest.skipUnless(shell_theme.find_compiler(), "no Sass compiler")
class ShellThemeTest(unittest.TestCase):
    def build(self, flavor="mocha", accent="teal", **options):
        return shell_theme.build_css(SOURCES, flavor, accent, ShellOptions(**options))

    def test_every_flavor_replaces_adwaita_and_bakes_the_accent_in(self):
        for flavor in palette.FLAVORS:
            css = self.build(flavor, "mauve")
            self.assertEqual(css.count("{"), css.count("}"), flavor)
            self.assertNotIn("st-accent", css, flavor)
            self.assertIsNone(ADWAITA.search(css), flavor)
            self.assertGreater(css.count(palette.color(flavor, "mauve")), 100, flavor)

    def test_mocha(self):
        r = rules(self.build("mocha", "teal"))
        self.assertEqual(r["stage"]["color"], "#cdd6f4")
        self.assertEqual(r["#panel"]["background-color"], "#11111b")
        self.assertEqual(r[".popup-menu-content"]["background-color"], "#1e1e2e")
        # what sits on the pastel accent is dark, including the handle of a switch
        self.assertEqual(r[".quick-toggle:checked"]["color"], "#1e1e2e")
        self.assertEqual(r[".toggle-switch:checked .handle"]["background"], "#1e1e2e")

    def test_latte_is_built_from_the_light_stylesheet(self):
        r = rules(self.build("latte", "teal"))
        self.assertEqual(r["stage"]["color"], "#4c4f69")
        self.assertEqual(r["#panel"]["background-color"], "#e6e9ef")
        self.assertEqual(r[".popup-menu-content"]["background-color"], "#e6e9ef")
        self.assertEqual(r[".quick-toggle:checked"]["background-color"], "#179299")
        self.assertEqual(r[".quick-toggle:checked"]["color"], "#eff1f5")
        self.assertEqual(r[".toggle-switch:checked .handle"]["background"], "white")

    def test_options_are_off_unless_asked_for(self):
        plain = self.build()
        self.assertNotIn("floating-panel", plain)
        self.assertNotIn("docked-panel", plain)
        self.assertNotIn("dashtodockContainer", plain)
        self.assertNotIn("st-mix(#94e2d5, #1e1e2e", plain)   # no accent tints without accent_selection
        self.assertEqual(self.build(panel_gap=10, panel_radius=4, docked_panel_opacity=0.5), plain)

    def test_opacity(self):
        r = rules(self.build(panel_opacity=0.7, popup_opacity=0.8))
        self.assertEqual(r["#panel"]["background-color"], "rgba(17, 17, 27, 0.7)")
        self.assertEqual(r[".popup-menu-content"]["background-color"], "rgba(30, 30, 46, 0.8)")
        # flat buttons no longer paint solid patches on the translucent popup
        self.assertEqual(r[".calendar .calendar-day"]["background-color"], "transparent")
        self.assertEqual(rules(self.build())[".calendar .calendar-day"]["background-color"], "#1e1e2e")

    def test_floating_panel(self):
        r = rules(self.build(floating_panel=True))
        self.assertEqual(r["#panel.floating-panel"], {"margin": "6px 6px 0 6px", "border-radius": "999px"})
        self.assertNotIn("#panel.docked-panel", r)
        r = rules(self.build(floating_panel=True, panel_gap=0, panel_radius=8, panel_opacity=0.5, docked_panel_opacity=1.0))
        self.assertEqual(r["#panel.floating-panel"], {"margin": "0px 0px 0 0px", "border-radius": "8px"})
        self.assertEqual(r["#panel"]["background-color"], "rgba(17, 17, 27, 0.5)")
        self.assertEqual(r["#panel.docked-panel"]["background-color"], "#11111b")
        self.assertEqual(r["#panel.docked-panel:overview"]["background-color"], "transparent")

    def test_no_blur_unless_asked_for(self):
        self.assertNotIn("gattuccino-blur", self.build())
        self.assertNotIn("gattuccino-blur", self.build(blur=False, blur_radius=40))

    def test_the_background_can_be_left_out_of_the_blur(self):
        r = rules(self.build(blur=True, blur_background=False))
        self.assertEqual(r["#panel"]["-gattuccino-blur-radius"], "32px")
        # GNOME's own solid background is left on the overview, so there is nothing to see through
        self.assertEqual(r["#overviewGroup"], {"background-color": "#1e1e2e"})
        self.assertNotIn("-gattuccino-blur-radius", r.get(".screen-shield-background", {}))

    def test_the_background_has_a_blur_of_its_own(self):
        r = rules(self.build(blur=True, blur_radius=40, blur_background_radius=12))
        self.assertEqual(r["#panel"]["-gattuccino-blur-radius"], "40px")
        self.assertEqual(r["#overviewGroup"]["-gattuccino-blur-radius"], "12px")
        # the lock screen says only how far: the Shell's own dimming stays
        self.assertEqual(r[".screen-shield-background"]["-gattuccino-blur-radius"], "12px")
        self.assertNotIn("-gattuccino-blur-brightness", r[".screen-shield-background"])

    def test_blur_leaves_the_colors_of_the_surfaces_alone(self):
        options = dict(panel_opacity=0.8, popup_opacity=0.8, floating_panel=True,
                       docked_panel_opacity=0.9, dock_like_panel=True)
        plain = rules(self.build(**options))
        blurred = rules(self.build(blur=True, **options))
        for surface in ("#panel", ".popup-menu-content", "#panel.docked-panel",
                        "#dashtodockContainer #dash .dash-background"):
            self.assertEqual(blurred[surface]["background-color"],
                             plain[surface]["background-color"], surface)

    def test_blur_states_what_the_extension_should_blur(self):
        r = rules(self.build(blur=True, blur_radius=40, panel_opacity=0.8, popup_opacity=0.8))
        for surface in ("#panel", ".popup-menu-content"):
            self.assertEqual(r[surface]["-gattuccino-blur-radius"], "40px", surface)
            self.assertEqual(r[surface]["-gattuccino-blur-brightness"], "1", surface)
        # the dock only has them when the theme styles the dock at all
        self.assertNotIn("#dashtodockContainer #dash .dash-background", r)
        r = rules(self.build(blur=True, dock_like_panel=True))
        self.assertEqual(r["#dashtodockContainer #dash .dash-background"]["-gattuccino-blur-radius"], "32px")

        # plain glass leaves the colors of the surfaces as they are
        self.assertEqual(r["#panel"]["background-color"], "#11111b")

    def test_blur_turns_the_overview_into_glass(self):
        plain = rules(self.build())
        self.assertEqual(plain["#overviewGroup"], {"background-color": "#1e1e2e"})

        r = rules(self.build(blur=True, blur_background_radius=30))
        self.assertEqual(r["#overviewGroup"]["background-color"], "rgba(30, 30, 46, 0.4)")
        # a little dimming of its own
        self.assertEqual(r["#overviewGroup"]["-gattuccino-blur-radius"], "30px")
        self.assertEqual(r["#overviewGroup"]["-gattuccino-blur-brightness"], "0.9")
        self.assertEqual(r["#panel"]["-gattuccino-blur-brightness"], "1")

    def test_accent_selection(self):
        accent, fg = palette.color("mocha", "teal"), palette.color("mocha", "base")
        r = rules(self.build(accent_selection=True))

        # a selected tile takes the accent itself, with a text color to match
        self.assertEqual(r[".switcher-list .item-box:selected"], {"background-color": accent, "color": fg})

        # everything that merely highlights gets a tint of it
        self.assertEqual(r[".calendar .calendar-day:hover"]["background-color"],
                         f"st-mix({accent}, {palette.color('mocha', 'base')}, 20%)")
        self.assertEqual(r["#panel .panel-button:hover"]["box-shadow"],
                         "inset 0 0 0 100px rgba(148, 226, 213, 0.25)")

        # menu items among them, and they keep the shell's own text color: the
        # accent itself left the text on top of it without contrast
        for state, tint in (("hover", 20), ("selected", 20), ("active", 32)):
            item = r[f".popup-menu-item:{state}"]
            self.assertTrue(item["background-color"].startswith(f"st-mix({accent}, "), (state, item))
            self.assertTrue(item["background-color"].endswith(f", {tint}%)"), (state, item))
            self.assertEqual(item["color"], palette.color("mocha", "text"), state)

    def test_accent_selection_follows_the_flavor_and_the_accent(self):
        r = rules(self.build(flavor="latte", accent="mauve", accent_selection=True))
        mauve = palette.color("latte", "mauve")
        self.assertTrue(r[".popup-menu-item:hover"]["background-color"].startswith(f"st-mix({mauve}, "))
        self.assertEqual(r[".popup-menu-item:hover"]["color"], palette.color("latte", "text"))
        self.assertEqual(r[".switcher-list .item-box:selected"],
                         {"background-color": mauve, "color": palette.color("latte", "base")})
        self.assertEqual(r["#panel .panel-button:hover"]["box-shadow"],
                         "inset 0 0 0 100px rgba(136, 57, 239, 0.25)")

    def test_dock_like_panel(self):
        dock = "#dashtodockContainer #dash "
        plain = rules(self.build(panel_opacity=0.7))
        r = rules(self.build(panel_opacity=0.7, dock_like_panel=True))
        # only rules inside Dash to Dock's container are added: the overview's dash is untouched
        added = set(r) - set(plain)
        self.assertTrue(added and all(selector.startswith(dock) for selector in added))
        self.assertEqual({s: r[s] for s in plain}, plain)
        self.assertEqual(r[dock + ".dash-background"]["background-color"], r["#panel"]["background-color"])
        self.assertEqual(r[dock + ".dash-background"]["background-color"], "rgba(17, 17, 27, 0.7)")
        self.assertEqual(r[dock + ".dash-item-container .overview-tile .overview-icon"],
                         {"color": "#cdd6f4", "background-color": "transparent"})
        self.assertEqual(r[dock + ".dash-item-container .app-grid-running-dot"]["background-color"], "#cdd6f4")

        # opaque when the top bar is, and dark icons and dots on Latte's light bar
        r = rules(self.build("latte", dock_like_panel=True))
        self.assertEqual(r[dock + ".dash-background"]["background-color"], "#e6e9ef")
        self.assertEqual(r[dock + ".dash-item-container .show-apps .overview-icon"]["color"], "#4c4f69")
        self.assertEqual(r[dock + ".dash-item-container .app-grid-running-dot"]["background-color"], "#4c4f69")
        self.assertNotEqual(r["#dash .dash-background"]["background-color"], "#e6e9ef")

    def test_dock_accent(self):
        accent, on_accent = palette.color("mocha", "teal"), palette.color("mocha", "base")
        item = "#dashtodockContainer #dash .dash-item-container"
        css = shell_theme.dock_accent_css("mocha", "teal")
        r = rules(css)

        # every rule is inside Dash to Dock's container: the overview's dash keeps the theme's colors
        self.assertTrue(all(selector.startswith("#dashtodockContainer #dash ") for selector in r), sorted(r))
        # and every one of them says !important, the only way past Dash to Dock's own stylesheet
        self.assertTrue(all(value.endswith(" !important")
                            for declarations in r.values() for value in declarations.values()), css)

        # the application in focus looks like a hovered one: a light accent, and no more
        light = {"background-color": f"st-transparentize({accent}, 0.7) !important"}
        for selector in (".overview-tile.focused", ".overview-tile:hover", ".show-apps:hover"):
            self.assertEqual(r[f"{item} {selector} .overview-icon"], light, selector)
        self.assertEqual(r[f"{item} .overview-tile:active .overview-icon"]["background-color"],
                         f"st-transparentize({accent}, 0.55) !important")
        # the windows counter indicators, in the color of the dot they stand in for
        self.assertEqual(r[f"{item} .app-grid-running-dot"]["background-color"], f"{accent} !important")
        self.assertEqual(r["#dashtodockContainer #dash .notification-badge"],
                         {"background-color": f"{accent} !important", "color": f"{on_accent} !important"})

    def test_dock_icon_is_drawn_in_its_own_colors(self):
        r = rules(shell_theme.dock_icon_css())
        self.assertEqual(r["#dashtodockContainer #dash .show-apps-icon"], {"-st-icon-style": "regular !important"})
        self.assertEqual(r["#dashtodockContainer #dash .show-apps StIcon"], {"-st-icon-style": "regular !important"})

    def test_dock_shape(self):
        r = rules(shell_theme.dock_shape_css("round"))
        # as round as the floating top bar, past Dash to Dock's own radius
        self.assertEqual(r["#dashtodockContainer #dash .dash-background"], {"border-radius": "999px !important"})
        # and a dock extended over the whole edge stays square
        self.assertEqual(r["#dashtodockContainer.extended #dash .dash-background"]["border-radius"], "0 !important")
        # room at the ends of the dock, along the edge it is on, so that the icons clear the curve
        for edge, sides in (("bottom", ("left", "right")), ("top", ("left", "right")),
                            ("left", ("top", "bottom")), ("right", ("top", "bottom"))):
            declarations = r[f"#dashtodockContainer.{edge} #dash .dash-background"]
            self.assertEqual(declarations, {f"padding-{side}": "15px !important" for side in sides}, edge)
        r = rules(shell_theme.dock_shape_css(12))
        self.assertEqual(r["#dashtodockContainer #dash .dash-background"]["border-radius"], "12px !important")
        self.assertEqual(r["#dashtodockContainer.bottom #dash .dash-background"]["padding-left"], "6px !important")

    def test_lock_screen_accent(self):
        accent, on_accent = palette.color("mocha", "teal"), palette.color("mocha", "base")
        r = rules(shell_theme.lock_accent_css("mocha", "teal"))
        entry = ".unlock-dialog .login-dialog-prompt-entry"
        self.assertEqual(r[entry], {"caret-color": accent, "selection-background-color": accent,
                                    "selected-color": on_accent})
        self.assertEqual(r[entry + ":focus"]["box-shadow"],
                         f"inset 0 0 0 2px st-transparentize({accent}, 0.2) !important")
        # nothing but the lock screen's password field is touched
        self.assertTrue(all(selector.startswith(entry) for selector in r), sorted(r))

    def test_lock_screen_accent_follows_the_flavor_and_the_accent(self):
        css = shell_theme.lock_accent_css("latte", "mauve")
        self.assertIn("flavor=latte, accent=mauve", css)
        self.assertIn(palette.color("latte", "mauve"), css)
        self.assertNotIn(palette.color("mocha", "mauve"), css)

    def test_dock_accent_follows_the_flavor_and_the_accent(self):
        css = shell_theme.dock_accent_css("latte", "mauve")
        self.assertIn("flavor=latte, accent=mauve", css)
        self.assertIn(f"background-color: {palette.color('latte', 'mauve')} !important", css)
        self.assertIn(f"color: {palette.color('latte', 'base')} !important", css)
        self.assertNotIn(palette.color("mocha", "mauve"), css)

    def test_sources_that_are_not_gnome_shell(self):
        with self.assertRaises(shell_theme.BuildError):
            shell_theme.build_css(__file__.rsplit("/", 1)[0], "mocha", "teal", ShellOptions())


if __name__ == "__main__":
    unittest.main()


class WriteThemeIconTest(unittest.TestCase):
    """The icon a theme carries, which the extension puts on the dock when the theme is selected."""

    def write(self, **options):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        shell_theme.write_theme(f"{directory.name}/theme", "/* css */", "mocha", "teal", "49.2", **options)
        return directory.name

    def test_the_icon_goes_with_the_theme_under_a_name_of_its_own(self):
        directory = self.write()
        self.assertEqual(os.listdir(f"{directory}/theme/gnome-shell"), ["gnome-shell.css"])

        for name in ("apps.svg", "apps.PNG"):
            source = f"{directory}/{name}"
            with open(source, "w") as f:
                f.write(name)
            theme = self.write(show_apps_icon_file=source)
            self.assertIn(f"show-apps-icon{os.path.splitext(name)[1].lower()}", os.listdir(f"{theme}/theme/gnome-shell"))
