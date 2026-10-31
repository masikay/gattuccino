import re
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
