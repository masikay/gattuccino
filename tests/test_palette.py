import re
import unittest

from gattuccino import palette


class PaletteTest(unittest.TestCase):
    def test_every_flavor_has_the_same_26_colors(self):
        names = list(palette.FLAVORS["mocha"])
        self.assertEqual(len(names), 26)
        for flavor, colors in palette.FLAVORS.items():
            self.assertEqual(list(colors), names, flavor)
            for value in colors.values():
                self.assertRegex(value, r"^#[0-9a-f]{6}$")
        self.assertEqual(set(palette.DARK), set(palette.FLAVORS))
        self.assertEqual([f for f, dark in palette.DARK.items() if not dark], ["latte"])

    def test_accents(self):
        self.assertEqual(len(palette.ACCENTS), 14)
        self.assertEqual(list(palette.FLAVORS["mocha"])[:14], list(palette.ACCENTS))
        # GNOME's nine accents each get a different Catppuccin accent
        self.assertEqual(list(palette.SETTINGS_ACCENTS),
                         ["blue", "teal", "green", "yellow", "orange", "red", "pink", "purple", "slate"])
        self.assertEqual(len(set(palette.SETTINGS_ACCENTS.values())), 9)
        self.assertLessEqual(set(palette.SETTINGS_ACCENTS.values()), set(palette.ACCENTS))

    def test_helpers(self):
        self.assertEqual(palette.color("mocha", "teal"), "#94e2d5")
        self.assertEqual(palette.color("latte", "text"), "#4c4f69")
        self.assertEqual(palette.rgba("mocha", "text", 0.08), "rgba(205, 214, 244, 0.08)")
        self.assertTrue(re.fullmatch(r"rgba\(\d+, \d+, \d+, 0\.2\)", palette.rgba("latte", "base", 0.2)))


if __name__ == "__main__":
    unittest.main()
