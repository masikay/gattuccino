import re
import unittest

from gattuccino import gtk_theme, palette

DECLARATION = re.compile(r"(--[a-z0-9-]+: |@define-color [a-z0-9_]+ )(#[0-9a-f]{6}|rgba\(\d+, \d+, \d+, [0-9.]+\));")


def declarations(css):
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [line.strip() for line in body.splitlines() if line.strip()]


class GtkThemeTest(unittest.TestCase):
    def test_every_file_is_well_formed_and_marked(self):
        for flavor in palette.DARK_FLAVORS:
            for dark in (True, False):
                for selection in (True, False):
                    contents_by_folder = gtk_theme.files(flavor, dark, "mauve", "follow", selection)
                    for folder, contents in contents_by_folder.items():
                        expected = ["gtk.css", gtk_theme.ACCENT_FILE, "gattuccino-latte.css",
                                    f"gattuccino-{flavor}.css"]
                        self.assertEqual(sorted(contents),
                                         sorted(expected + [gtk_theme.SELECTION_FILE] if selection else sorted(expected)))
                        for name, css in contents.items():
                            self.assertTrue(css.startswith(gtk_theme.MARKER), (flavor, folder, name))
                            if name == gtk_theme.SELECTION_FILE:
                                continue  # rules, not declarations: checked on its own below
                            for line in declarations(css):
                                if line in (":root {", "}") or line.startswith("@import url(\"gattuccino-"):
                                    continue
                                self.assertRegex(line, DECLARATION, (flavor, folder, name))

    def test_gtk_css_imports_the_flavor_of_the_style_and_the_accent(self):
        dark = gtk_theme.gtk_css("frappe", dark=True)
        self.assertTrue(dark.startswith("/* gattuccino: style (light=latte, dark=frappe)\n"))
        self.assertEqual([l for l in declarations(dark)],
                         ['@import url("gattuccino-frappe.css");', '@import url("gattuccino-accent.css");'])
        light = gtk_theme.gtk_css("frappe", dark=False)
        self.assertIn('@import url("gattuccino-latte.css");', light)
        self.assertEqual(light.splitlines()[0], dark.splitlines()[0])
        files = gtk_theme.files("frappe", False, "teal", "follow", False)
        self.assertEqual(files["gtk-3.0"]["gtk.css"], light)
        # the accent file is in the flavor of the style
        self.assertIn(palette.color("latte", "teal"), files["gtk-4.0"][gtk_theme.ACCENT_FILE])
        self.assertIn(palette.color("frappe", "teal"), gtk_theme.files("frappe", True, "teal", "follow", False)["gtk-4.0"][gtk_theme.ACCENT_FILE])

    def test_flavor_files(self):
        css = gtk_theme.gtk4_css("latte", picker_swatches=True, selection=False)
        lines = declarations(css)
        self.assertIn("--window-bg-color: #eff1f5;", lines)
        self.assertIn("--window-fg-color: #4c4f69;", lines)
        self.assertIn("@define-color window_bg_color #eff1f5;", lines)
        self.assertIn("--accent-purple: #8839ef; /* mauve */", css)
        self.assertNotIn("@import", css)
        self.assertNotIn("accent-bg-color", css)
        self.assertNotIn("accent_bg_color", css)
        self.assertIn("Adwaita light style", css)
        self.assertIn("Adwaita dark style", gtk_theme.gtk4_css("mocha", True, False))
        # with a fixed accent, the picker's swatches keep GNOME's colors
        self.assertNotIn("--accent-purple", gtk_theme.gtk4_css("latte", picker_swatches=False, selection=False))
        self.assertNotIn("--accent-purple", gtk_theme.files("mocha", True, "sky", "sky", False)["gtk-4.0"]["gattuccino-latte.css"])

    def test_gtk3_only_uses_named_colors(self):
        css = gtk_theme.gtk3_css("mocha", False)
        self.assertNotIn(":root", css)
        self.assertNotIn("--", re.sub(r"/\*.*?\*/", "", css, flags=re.S))
        self.assertIn("@define-color headerbar_bg_color #181825;", css)
        self.assertIn("adw-gtk3-dark", css)
        self.assertIn("the adw-gtk3 theme", gtk_theme.gtk3_css("latte", False))

    def test_accent_files(self):
        css = gtk_theme.gtk4_accent_css("mocha", "teal", "follow")
        self.assertTrue(css.startswith("/* gattuccino: accent (flavor=mocha, accent=follow)\n"))
        self.assertIn("  --accent-bg-color: #94e2d5;\n  --accent-fg-color: #1e1e2e;\n  --accent-color: #94e2d5;\n", css)
        self.assertTrue(css.endswith("@define-color accent_color #94e2d5;\n"))
        gtk3 = gtk_theme.gtk3_accent_css("latte", "peach", "peach")
        self.assertTrue(gtk3.startswith("/* gattuccino: accent (flavor=latte, accent=peach)\n"))
        self.assertNotIn(":root", gtk3)
        self.assertIn("@define-color accent_bg_color #fe640b;\n@define-color accent_fg_color #eff1f5;\n", gtk3)

    def test_selection_files_hold_the_rules_for_rows_and_menu_items(self):
        gtk4 = gtk_theme.gtk4_selection_css()
        self.assertTrue(gtk4.startswith("/* gattuccino: selection\n"))
        self.assertIn(".navigation-sidebar row:selected,", gtk4)
        # only a selected row takes the accent itself, with a text color to match
        self.assertIn("background-color: var(--accent-bg-color);", gtk4)
        self.assertIn("color: var(--accent-fg-color);", gtk4)
        # hovering an unselected row only tints, and must not fight the selected rule
        self.assertIn(".navigation-sidebar row.activatable:not(:selected):hover,", gtk4)
        self.assertIn("background-color: color-mix(in srgb, var(--accent-bg-color) 20%, transparent);", gtk4)

        # A menu item is tinted and keeps the text color the application gave it:
        # some applications draw their own text over it, and the accent itself
        # left them without contrast.
        self.assertIn("popover.menu modelbutton:not(:disabled):hover,\n"
                      "popover.menu modelbutton:not(:disabled):selected {\n"
                      "  background-color: color-mix(in srgb, var(--accent-bg-color) 20%, transparent);\n"
                      "}\n", gtk4)

        # Selected text is named without transparency, for applications that read
        # the color rather than let GTK paint it, and its glyphs are drawn again:
        # an opaque background on its own covers the text GNOME paints underneath.
        self.assertIn("selection {\n"
                      "  background-color: color-mix(in srgb, var(--view-fg-color) 10%,"
                      " var(--view-bg-color));\n"
                      "  color: currentColor;\n"
                      "}\n", gtk4)
        self.assertIn("selection:focus-within {\n"
                      "  background-color: color-mix(in srgb, var(--accent-bg-color) 30%,"
                      " var(--view-bg-color));\n"
                      "}\n", gtk4)

        # GTK 3 gets the hover and the menu items: no pseudo-class there matches
        # a selected row
        gtk3 = gtk_theme.gtk3_selection_css()
        self.assertIn("menu menuitem:hover,", gtk3)
        self.assertIn(".sidebar row.activatable:hover,", gtk3)
        self.assertIn("background-color: alpha(@accent_bg_color, 0.2);", gtk3)
        self.assertNotIn(":selected", gtk3)
        # nothing in GTK 3 forces a text color either
        self.assertNotIn("color: @accent_fg_color;", gtk3)
        # GTK 3 has no custom properties, GTK 4 no @define-color colors
        self.assertNotIn("--accent", gtk3)
        self.assertNotIn("@accent", gtk4)

    def test_the_selection_files_do_not_depend_on_the_flavor_or_the_accent(self):
        """So the accent extension never has to rewrite them, and need not know them."""
        for folder in ("gtk-4.0", "gtk-3.0"):
            written = {gtk_theme.files(flavor, dark, accent, "follow", True)[folder][gtk_theme.SELECTION_FILE]
                       for flavor in palette.DARK_FLAVORS for dark in (True, False)
                       for accent in ("teal", "peach")}
            self.assertEqual(len(written), 1, folder)

    def test_only_the_flavor_files_import_the_selection_rules(self):
        """gtk.css is rewritten by the extension, the flavor files never are."""
        for folder, contents in gtk_theme.files("mocha", True, "teal", "follow", True).items():
            self.assertNotIn(gtk_theme.SELECTION_FILE, contents["gtk.css"], folder)
            for flavor in ("latte", "mocha"):
                self.assertIn(f'@import url("{gtk_theme.SELECTION_FILE}");',
                              contents[gtk_theme.flavor_file(flavor)], (folder, flavor))
        off = gtk_theme.files("mocha", True, "teal", "follow", False)
        for folder, contents in off.items():
            self.assertNotIn(gtk_theme.SELECTION_FILE, "".join(contents.values()), folder)


if __name__ == "__main__":
    unittest.main()
