import os
import tempfile
import unittest

from gattuccino import preferences as prefs


class PreferencesTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "sub", "preferences.ini")

    def test_defaults(self):
        p = prefs.load(self.path)   # no file yet
        self.assertEqual((p.flavor, p.accent, p.shell_theme, p.gtk_theme, p.flatpak), ("mocha", "follow", True, True, False))
        self.assertEqual((p.panel_opacity, p.popup_opacity, p.floating_panel, p.dock_like_panel), (1.0, 1.0, False, False))
        self.assertTrue(p.follows_picker)

    def test_round_trip(self):
        p = prefs.Preferences()
        for name, text in [("flavor", "Frappe"), ("accent", "peach"), ("flatpak", "YES"), ("popup_opacity", "0.8"),
                           ("floating_panel", "on"), ("dock_like_panel", "y"), ("panel_radius", "12"), ("docked_panel_opacity", "1"),
                           ("shell_version", "49.2")]:
            p.set(name, text)
        prefs.save(p, self.path)
        self.assertEqual(prefs.load(self.path), p)
        self.assertEqual((p.flavor, p.flatpak, p.panel_radius, p.docked_panel_opacity), ("frappe", True, 12, 1.0))
        self.assertFalse(p.follows_picker)

        defaults = prefs.Preferences()
        prefs.save(defaults, self.path)
        self.assertEqual(prefs.load(self.path), defaults)
        self.assertEqual((defaults.text("panel_radius"), defaults.text("docked_panel_opacity"), defaults.text("panel_opacity")),
                         ("round", "same", "1"))

    def test_wrong_values_are_refused_and_change_nothing(self):
        p = prefs.Preferences()
        for name, text in [("flavor", "dark"), ("flavor", "latte"), ("accent", "grey"), ("panel_opacity", "2"), ("popup_opacity", "half"),
                           ("panel_gap", "13"), ("panel_radius", "big"), ("flatpak", "maybe"), ("docked_panel_opacity", "-1"),
                           ("shell_version", "47.1"), ("shell_version", "latest")]:
            with self.assertRaises(prefs.PreferenceError, msg=f"{name}={text}") as raised:
                p.set(name, text)
            self.assertIn(name.replace("_", "-"), str(raised.exception))
        self.assertEqual(p, prefs.Preferences())

    def test_a_file_edited_by_hand(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("[preferences]\nflavor = frappe\n")   # the rest keeps its defaults
        self.assertEqual(prefs.load(self.path).flavor, "frappe")
        with open(self.path, "w") as f:
            f.write("[preferences]\nflavor = latte\n")   # from an earlier version: latte is now always there
        self.assertEqual(prefs.load(self.path).flavor, "mocha")
        with open(self.path, "w") as f:
            f.write("[preferences]\nflavour = frappe\n")
        with self.assertRaisesRegex(prefs.PreferenceError, "unknown preference 'flavour'"):
            prefs.load(self.path)
        with open(self.path, "w") as f:
            f.write("[preferences]\npanel_opacity = 7\n")
        with self.assertRaisesRegex(prefs.PreferenceError, "panel-opacity"):
            prefs.load(self.path)


if __name__ == "__main__":
    unittest.main()
