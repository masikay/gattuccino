"""Runs the extensions' own tests (Node.js), and checks that the accent
extension and the installer agree on colors and on the files they both write."""

import glob
import json
import os
import re
import shutil
import subprocess
import unittest

from gattuccino import gtk_theme, install, palette

from .support import ROOT

EXTENSIONS = os.path.join(ROOT, "extensions")
TESTS = os.path.join(ROOT, "tests", "extensions")


class ExtensionFilesTest(unittest.TestCase):
    def test_metadata(self):
        for uuid in (install.FLOATING_PANEL_UUID, install.ACCENT_UUID):
            with open(f"{EXTENSIONS}/{uuid}/metadata.json") as f:
                metadata = json.load(f)
            self.assertEqual(metadata["uuid"], uuid)
            self.assertIn("48", metadata["shell-version"])
            self.assertTrue(os.path.exists(f"{EXTENSIONS}/{uuid}/extension.js"))
        self.assertEqual(sorted(os.listdir(EXTENSIONS)), sorted([install.FLOATING_PANEL_UUID, install.ACCENT_UUID]))

    def test_the_accent_extension_has_the_palette(self):
        with open(f"{EXTENSIONS}/{install.ACCENT_UUID}/extension.js") as f:
            source = f.read()
        names = dict(re.findall(r"(\w+): '(\w+)'", source.split("const ACCENT_NAMES = {")[1].split("};")[0]))
        self.assertEqual(names, palette.SETTINGS_ACCENTS)
        table = source.split("const FLAVORS = {")[1].split("\n};")[0]
        for flavor, block in re.findall(r"(\w+): \{(.*?)\n    \}", table, flags=re.S):
            colors = dict(re.findall(r"(\w+): '(#[0-9a-f]{6})'", block))
            expected = {name: palette.color(flavor, name) for name in ["base", *palette.ACCENTS]}
            self.assertEqual(colors, expected, flavor)
        self.assertEqual(re.findall(r"^    (\w+): \{$", table, flags=re.M), list(palette.FLAVORS))

    def test_the_gap_stays_below_the_distance_that_docks_the_panel(self):
        from gattuccino import preferences
        with open(f"{EXTENSIONS}/{install.FLOATING_PANEL_UUID}/extension.js") as f:
            proximity = int(re.search(r"const PROXIMITY = (\d+);", f.read()).group(1))
        with self.assertRaises(preferences.PreferenceError):
            preferences.Preferences().set("panel_gap", str(proximity))
        preferences.Preferences().set("panel_gap", "12")
        self.assertLess(12, proximity)


@unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
class ExtensionBehaviorTest(unittest.TestCase):
    def test_extension_tests(self):
        result = subprocess.run(["node", "--test", *sorted(glob.glob(f"{TESTS}/*.test.mjs"))],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_extension_writes_the_same_accent_files_as_the_installer(self):
        result = subprocess.run(["node", f"{TESTS}/print-accent-files.mjs"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        written = json.loads(result.stdout)
        self.assertEqual(list(written), list(palette.FLAVORS))
        for flavor, by_accent in written.items():
            for picked, files in by_accent.items():
                accent = palette.SETTINGS_ACCENTS[picked]
                self.assertEqual(files["gtk-4.0"], gtk_theme.gtk4_accent_css(flavor, accent, "follow"), (flavor, picked))
                self.assertEqual(files["gtk-3.0"], gtk_theme.gtk3_accent_css(flavor, accent, "follow"), (flavor, picked))
                # gtk.css, in the style of the flavor (with mocha as the dark one for latte)
                dark_flavor = flavor if palette.DARK[flavor] else "mocha"
                self.assertEqual(files["gtk.css"], gtk_theme.gtk_css(dark_flavor, palette.DARK[flavor]), (flavor, picked))


if __name__ == "__main__":
    unittest.main()
