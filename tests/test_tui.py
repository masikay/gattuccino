"""The terminal screen, driven the way a person would: with keys."""

import copy
import unittest

from gattuccino import preferences as prefs

try:
    from gattuccino import tui
    from textual.widgets import Input, Select, Switch
except ImportError:   # Textual is not installed
    tui = None


@unittest.skipUnless(tui, "Textual is not installed")
class TuiTest(unittest.IsolatedAsyncioTestCase):
    async def test_every_group_shows_its_preferences(self):
        app = tui.ConfigApp(prefs.Preferences())
        async with app.run_test(size=(120, 50)) as pilot:
            for group, names in prefs.GROUPS:
                await app.show_group(group)
                await pilot.pause()
                shown = {widget.id.removeprefix("opt-") for widget in app.query("*")
                         if (widget.id or "").startswith("opt-")}
                wanted = {name for name in names
                          if prefs.visible(next(f for f in app.fields if f.name == name), app.preferences)}
                self.assertEqual(shown, wanted, group)

    async def test_the_arrow_keys_move_between_groups(self):
        app = tui.ConfigApp(prefs.Preferences())
        async with app.run_test(size=(120, 50)) as pilot:
            self.assertEqual(app.group, "Colors")
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(app.group, "Top bar")
            await pilot.press("down", "down")
            await pilot.pause()
            self.assertEqual(app.group, "Blur")

    async def test_a_switch_changes_a_preference_and_shows_what_depends_on_it(self):
        app = tui.ConfigApp(prefs.Preferences())
        async with app.run_test(size=(120, 50)) as pilot:
            await app.show_group("Blur")
            await pilot.pause()
            self.assertEqual(len(app.query("#opt-blur_radius")), 0)   # there is no blur to size yet
            app.query_one("#opt-blur", Switch).toggle()
            await pilot.pause()
            self.assertTrue(app.preferences.blur)
            self.assertEqual(len(app.query("#opt-blur_radius")), 1)
            self.assertTrue(app.dirty)

    async def test_a_value_that_is_not_allowed_is_refused_and_says_why(self):
        app = tui.ConfigApp(prefs.Preferences())
        async with app.run_test(size=(120, 50)) as pilot:
            await app.show_group("Top bar")
            await pilot.pause()
            box = app.query_one("#opt-panel_opacity", Input)
            box.value = "7"
            await pilot.pause()
            self.assertEqual(app.preferences.panel_opacity, 1.0)
            self.assertIn("between 0", str(app.query_one("#err-panel_opacity").render()))
            box.value = "0.8"
            await pilot.pause()
            self.assertEqual(app.preferences.panel_opacity, 0.8)
            self.assertEqual(str(app.query_one("#err-panel_opacity").render()), "")

    async def test_a_choice_is_taken_from_the_list(self):
        app = tui.ConfigApp(prefs.Preferences())
        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause()
            app.query_one("#opt-flavor", Select).value = "frappe"
            await pilot.pause()
            self.assertEqual(app.preferences.flavor, "frappe")

    async def test_save_and_apply_come_back_with_what_was_chosen(self):
        for key, action in (("ctrl+s", tui.SAVE), ("ctrl+a", tui.APPLY)):
            app = tui.ConfigApp(prefs.Preferences())
            async with app.run_test(size=(120, 50)) as pilot:
                await pilot.pause()
                app.query_one("#opt-flavor", Select).value = "macchiato"
                await pilot.pause()
                await pilot.press(key)
            self.assertEqual(app.return_value.action, action)
            self.assertEqual(app.return_value.preferences.flavor, "macchiato")

    async def test_leaving_with_changes_asks_first_and_changes_nothing(self):
        original = prefs.Preferences()
        app = tui.ConfigApp(copy.deepcopy(original))
        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause()
            app.query_one("#opt-flavor", Select).value = "frappe"
            await pilot.pause()
            await pilot.press("ctrl+q")
            await pilot.pause()
            self.assertIsInstance(app.screen, tui.Confirm)   # asked, and still there
            await pilot.click("#yes")
            await pilot.pause()
        self.assertIsNone(app.return_value.action)
        self.assertEqual(app.return_value.preferences, original)

    async def test_leaving_without_changes_does_not_ask(self):
        app = tui.ConfigApp(prefs.Preferences())
        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+q")
            await pilot.pause()
        self.assertIsNone(app.return_value.action)
