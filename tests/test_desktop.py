import os
import unittest

from gattuccino.desktop import Desktop

from .support import USER_THEME_UUID, FakeHome


class FlatpakFileTest(unittest.TestCase):
    """Taking folders back out of Flatpak's overrides file."""

    def setUp(self):
        self.home = FakeHome(commands=())
        self.addCleanup(self.home.close)
        self.desktop = Desktop(self.home.env)
        os.makedirs(os.path.dirname(self.home.flatpak_file))

    def write(self, text):
        with open(self.home.flatpak_file, "w") as f:
            f.write(text)

    def test_reading(self):
        self.assertEqual(self.desktop.flatpak_filesystems(), [])   # no file
        self.write("[Environment]\nfilesystems=not-this;\n\n[Context]\nsockets=x11;\nfilesystems=~/Games;xdg-config/gtk-4.0:ro;\n")
        self.assertEqual(self.desktop.flatpak_filesystems(), ["~/Games", "xdg-config/gtk-4.0:ro"])

    def test_removing_keeps_everything_else(self):
        self.write("[Context]\nsockets=x11;\nfilesystems=~/Games;xdg-config/gtk-4.0:ro;xdg-config/gtk-3.0:ro;\n\n[Environment]\nFOO=bar\n")
        self.desktop.flatpak_remove_filesystems(["xdg-config/gtk-4.0:ro", "xdg-config/gtk-3.0:ro"])
        self.assertEqual(self.home.read(self.home.flatpak_file),
                         "[Context]\nsockets=x11;\nfilesystems=~/Games;\n\n[Environment]\nFOO=bar\n")

    def test_removing_the_last_folder_drops_the_key_then_the_section_then_the_file(self):
        self.write("[Context]\nsockets=x11;\nfilesystems=xdg-config/gtk-4.0:ro;\n")
        self.desktop.flatpak_remove_filesystems(["xdg-config/gtk-4.0:ro"])
        self.assertEqual(self.home.read(self.home.flatpak_file), "[Context]\nsockets=x11;\n")

        self.write("[Context]\nfilesystems=xdg-config/gtk-4.0:ro;\n\n[Environment]\nFOO=bar\n")
        self.desktop.flatpak_remove_filesystems(["xdg-config/gtk-4.0:ro"])
        self.assertEqual(self.home.read(self.home.flatpak_file), "[Environment]\nFOO=bar\n")

        self.write("[Context]\nfilesystems=xdg-config/gtk-4.0:ro;\n")
        self.desktop.flatpak_remove_filesystems(["xdg-config/gtk-4.0:ro"])
        self.assertFalse(os.path.exists(self.home.flatpak_file))
        self.desktop.flatpak_remove_filesystems(["xdg-config/gtk-4.0:ro"])   # no file: nothing to do


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        self.addCleanup(self.home.close)
        self.desktop = Desktop(self.home.env)

    def test_values(self):
        d = self.desktop
        self.assertEqual(d.gsettings_get("org.gnome.desktop.interface", "accent-color"), "teal")
        self.assertEqual(d.gsettings_get("org.gnome.shell", "disabled-extensions"), [])
        self.assertIsNone(d.gsettings_get("org.example.missing", "key"))
        self.assertTrue(d.gsettings_set("org.gnome.desktop.interface", "color-scheme", "prefer-dark"))
        self.assertEqual(self.home.settings("org.gnome.desktop.interface", "color-scheme"), "prefer-dark")
        self.assertTrue(d.gsettings_set("org.gnome.shell", "enabled-extensions", []))
        self.assertEqual(self.home.settings("org.gnome.shell", "enabled-extensions"), [])

    def test_finding_the_user_themes_settings(self):
        self.assertEqual(self.desktop.user_theme_schema_args(),
                         ("--schemadir", f"{self.home.extensions}/{USER_THEME_UUID}/schemas"))
        self.home.set_user_themes("system")
        self.assertEqual(self.desktop.user_theme_schema_args(), ())
        other = FakeHome(user_themes="no")
        self.addCleanup(other.close)
        self.assertIsNone(Desktop(other.env).user_theme_schema_args())

    def test_enabling_an_extension_the_shell_does_not_know_yet(self):
        d, uuid = self.desktop, "new@example"
        self.home.set_setting("org.gnome.shell", "disabled-extensions", [uuid, "other@example"])
        self.assertTrue(d.enable_extension(uuid))    # takes effect at the next login
        self.assertEqual(self.home.settings("org.gnome.shell", "enabled-extensions"), [USER_THEME_UUID, uuid])
        self.assertEqual(self.home.settings("org.gnome.shell", "disabled-extensions"), ["other@example"])
        self.home.set_known_extensions([USER_THEME_UUID, uuid])
        self.assertFalse(d.enable_extension(uuid))   # known now: enabled at once
        d.disable_extension(uuid)
        self.assertEqual(self.home.settings("org.gnome.shell", "enabled-extensions"), [USER_THEME_UUID])


if __name__ == "__main__":
    unittest.main()
