"""The terminal menus of `gattuccino configure`: a screen with the groups of
preferences on the left and the preferences of the group on the right, to move
about with the arrow keys.

It needs Textual, which is not part of Python (Fedora packages it as
python3-textual, or `pip install textual`); without it `configure` asks its
questions one by one instead.
"""

import copy
from dataclasses import dataclass

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, OptionList, Select, Static, Switch
from textual.widgets.option_list import Option

from . import preferences as prefs

SAVE, APPLY = "save", "apply"


@dataclass
class Result:
    """What the screen came back with: the preferences, and what to do with them."""
    preferences: prefs.Preferences
    action: str = None   # SAVE, APPLY, or None for leaving them as they were


class Confirm(ModalScreen[bool]):
    """A question with a yes and a no."""

    BINDINGS = [("escape", "dismiss(False)", "No")]

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"):
            yield Label(self.question)
            with Horizontal():
                yield Button("Leave without saving", id="yes", variant="error")
                yield Button("Stay", id="no", variant="primary")

    @on(Button.Pressed)
    def answer(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")


class ConfigApp(App[Result]):
    TITLE = "Gattuccino"
    SUB_TITLE = "Catppuccin for GNOME"

    CSS = """
    #groups { width: 22; border-right: tall $primary-background; }
    #options { padding: 0 2; }
    .row { height: auto; margin-bottom: 1; }
    .switch-line { height: auto; }
    .switch-line Switch { border: none; padding: 0; height: 1; margin-right: 2; }
    .switch-line Label { padding-top: 0; }
    .name { text-style: bold; }
    .help { color: $text-muted; }
    .error { color: $error; }
    .live { color: $success; }
    Select, Input { width: 50; }
    #confirm { width: 60; height: auto; padding: 1 2; border: thick $error; background: $surface; }
    Confirm { align: center middle; }
    #confirm Horizontal { height: auto; margin-top: 1; }
    #confirm Button { margin-right: 2; }
    """

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("ctrl+a", "apply", "Save and apply"),
        ("ctrl+q", "quit_screen", "Quit"),
    ]

    def __init__(self, preferences: prefs.Preferences, path: str = ""):
        super().__init__()
        self.preferences = copy.deepcopy(preferences)
        self._saved = copy.deepcopy(preferences)
        self.path = path
        self.fields = prefs.all_fields()
        self.groups = [group for group, _ in prefs.GROUPS]
        self.group = self.groups[0]
        # In the colors of the flavor chosen, as far as Textual has them (all four)
        self.theme = f"catppuccin-{preferences.flavor}"

    # --- Layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield OptionList(*(Option(group, id=group) for group in self.groups), id="groups")
            yield VerticalScroll(id="options")
        yield Footer()

    async def on_mount(self):
        self.query_one("#groups", OptionList).highlighted = 0
        self.query_one("#groups", OptionList).focus()
        await self.show_group(self.group)

    @property
    def dirty(self) -> bool:
        return self.preferences != self._saved

    def _update_title(self):
        self.sub_title = "Catppuccin for GNOME" + ("  (changed)" if self.dirty else "")

    async def show_group(self, group: str):
        """The preferences of one group, the ones that depend on a switch only while it is on."""
        self.group = group
        container = self.query_one("#options", VerticalScroll)
        await container.remove_children()
        rows = [self._row(field) for field in self.fields
                if field.group == group and prefs.visible(field, self.preferences)]
        await container.mount(*rows)

    def _row(self, field: prefs.Field) -> Vertical:
        text = self.preferences.text(field.name)
        widgets = []
        if field.kind == prefs.SWITCH:
            widgets.append(Horizontal(Switch(value=getattr(self.preferences, field.name), id=f"opt-{field.name}"),
                                      Label(field.label, classes="name"), classes="switch-line"))
        elif field.kind == prefs.CHOICE:
            widgets.append(Label(field.label, classes="name"))
            widgets.append(Select([(choice, choice) for choice in field.choices], value=text,
                                  allow_blank=False, id=f"opt-{field.name}"))
        else:
            widgets.append(Label(field.label, classes="name"))
            widgets.append(Input(value=text, placeholder=field.spec.values, id=f"opt-{field.name}"))
        widgets.append(Static(field.spec.help, classes="help"))
        widgets.append(Static("", classes="error", id=f"err-{field.name}"))
        return Vertical(*widgets, classes="row")

    # --- Changes ------------------------------------------------------------

    @on(OptionList.OptionHighlighted, "#groups")
    async def group_chosen(self, event: OptionList.OptionHighlighted):
        if event.option.id != self.group:
            await self.show_group(event.option.id)

    def _commit(self, name: str, text: str) -> bool:
        """Take a value, or show what is wrong with it and keep the one there was."""
        error = self.query_one(f"#err-{name}", Static)
        trial = copy.deepcopy(self.preferences)
        try:
            trial.set(name, text)
        except prefs.PreferenceError as e:
            error.update(str(e))
            return False
        error.update("")
        setattr(self.preferences, name, getattr(trial, name))
        self._update_title()
        return True

    @on(Switch.Changed)
    async def switched(self, event: Switch.Changed):
        name = event.switch.id.removeprefix("opt-")
        if self._commit(name, "yes" if event.value else "no"):
            # The ones that depend on it come and go
            await self.show_group(self.group)
            self.query_one(f"#opt-{name}").focus()

    @on(Select.Changed)
    def selected(self, event: Select.Changed):
        self._commit(event.select.id.removeprefix("opt-"), str(event.value))

    @on(Input.Changed)
    def typed(self, event: Input.Changed):
        self._commit(event.input.id.removeprefix("opt-"), event.value)

    # --- Leaving ------------------------------------------------------------

    def action_save(self):
        self.exit(Result(self.preferences, SAVE))

    def action_apply(self):
        self.exit(Result(self.preferences, APPLY))

    def action_quit_screen(self):
        def left(leave: bool):
            if leave:
                self.exit(Result(self._saved, None))

        if self.dirty:
            self.push_screen(Confirm("There are changes that are not saved."), left)
        else:
            left(True)


def run(preferences: prefs.Preferences, path: str = "") -> Result:
    """Show the screen, and come back with what was chosen."""
    result = ConfigApp(preferences, path).run()
    return result if result is not None else Result(preferences, None)
