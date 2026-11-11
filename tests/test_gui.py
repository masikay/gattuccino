"""The window, built for real with GTK but never shown: its rows are changed the
way a person would, and what that does to the preferences is looked at."""

import os
import unittest

from gattuccino import preferences as prefs

from .support import FakeHome

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, Gtk
    from gattuccino import gui
    from gattuccino.controller import Controller
    from gattuccino.desktop import Desktop
    AVAILABLE = Gtk.init_check()
except (ImportError, ValueError):
    AVAILABLE = False


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child)
        child = child.get_next_sibling()


@unittest.skipUnless(AVAILABLE, "GTK 4 and libadwaita are not available, or there is no display")
class GuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Not unique on the bus: a window of the real one may be open
        cls.app = gui.Application(flags=Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)

    def setUp(self):
        self.home = FakeHome()
        self.addCleanup(self.home.close)
        self.desktop = Desktop(environment=self.home.env)
        self.controller = Controller(self.desktop)
        self.window = gui.PreferencesWindow(self.app, self.controller)

    def row(self, title):
        for widget in walk(self.window):
            if isinstance(widget, (Adw.SwitchRow, Adw.ComboRow, Adw.SpinRow, Adw.EntryRow)) \
                    and widget.get_title() == title:
                return widget
        raise AssertionError(f"no row called {title}")

    def saved(self):
        return prefs.load(self.desktop.preferences_path)

    def test_every_preference_has_a_row(self):
        titles = {w.get_title() for w in walk(self.window)
                  if isinstance(w, (Adw.SwitchRow, Adw.ComboRow, Adw.SpinRow, Adw.EntryRow))}
        for field in self.controller.fields:
            self.assertIn(field.label, titles, field.name)

    def test_a_switch_is_saved_and_shows_what_depends_on_it(self):
        radius = self.row("Blur radius")
        self.assertFalse(radius.get_visible())           # there is no blur to size yet
        self.row("Blur").set_active(True)
        self.assertTrue(self.saved().blur)
        self.assertTrue(radius.get_visible())

    def test_what_is_built_into_the_theme_waits_for_apply(self):
        self.assertFalse(self.window.apply_button.get_sensitive())
        self.row("Flavor").set_selected(0)   # frappe, the first of the dark flavors
        self.assertEqual(self.saved().flavor, "frappe")
        self.assertTrue(self.window.apply_button.get_sensitive())
        self.assertEqual(self.window.apply_button.get_label(), "Apply (1)")

    def test_what_the_extensions_change_while_they_run_does_not_wait(self):
        self.row("Panel gap").set_value(9)
        self.assertEqual(self.saved().panel_gap, 9)
        self.assertEqual(self.controller.pending, set())
        self.assertFalse(self.window.apply_button.get_sensitive())

    def test_a_number_that_may_be_a_word(self):
        choice, spin = self.row("Dock radius"), self.row("Dock radius, custom")
        self.assertFalse(spin.get_visible())              # Dash to Dock's own: no number
        choice.set_selected(1)                            # round
        self.assertEqual(self.saved().dock_radius, "round")
        choice.set_selected(2)                            # custom
        self.assertTrue(spin.get_visible())
        spin.set_value(18)
        self.assertEqual(self.saved().dock_radius, 18)

    def test_the_icon_of_the_dock_is_the_one_that_comes_with_the_project_unless_chosen(self):
        choice, entry = self.row("Show apps icon"), self.row("File")
        self.assertEqual(choice.get_selected(), 0)        # the icon of the flavor in use
        self.assertFalse(entry.get_visible())
        choice.set_selected(1)                            # GNOME's own
        self.assertEqual(self.saved().show_apps_icon, "gnome")
        choice.set_selected(2)                            # a file of one's own
        self.assertTrue(entry.get_visible())
        self.assertEqual(self.saved().show_apps_icon, "gnome")   # nothing to take before there is a file
        mine = os.path.join(self.home.home, "mine.svg")
        with open(mine, "w") as f:
            f.write("<svg/>")
        entry.set_text(mine)
        entry.emit("apply")
        self.assertEqual(self.saved().show_apps_icon, mine)
        choice.set_selected(0)
        self.assertIsNone(self.saved().show_apps_icon)

    def test_a_value_that_is_not_allowed_is_refused_and_marked(self):
        self.row("Show apps icon").set_selected(2)
        entry = self.row("File")
        entry.set_text(os.path.join(self.home.home, "missing.svg"))
        entry.emit("apply")
        self.assertTrue(entry.has_css_class("error"))
        self.assertIsNone(self.saved().show_apps_icon)
