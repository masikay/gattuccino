"""The window of `gattuccino gui`: the preferences, grouped, with a button to apply them.

GTK 4 and libadwaita (python3-gobject, which a GNOME session has). Each
preference is a row; the ones the extensions change while they run (marked
"live") take effect as the row is changed, and the rest wait for Apply.
"""

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import preferences as prefs  # noqa: E402
from .controller import ERRORS, Controller  # noqa: E402
from .desktop import Desktop  # noqa: E402

APP_ID = "org.gattuccino.Preferences"

ICONS = {
    "Colors": "color-select-symbolic",
    "Top bar": "view-more-horizontal-symbolic",
    "Dock": "view-app-grid-symbolic",
    "Blur": "weather-fog-symbolic",
    "Install": "system-software-install-symbolic",
}
# What a word that stands in place of a number is called
WORDS = {
    "round": "Round",
    "dock": "Dash to Dock's own",
    "same": "Same as the top bar",
}
CUSTOM = "Custom"


def number_text(value: float, digits: int) -> str:
    """A number as a preference is typed: no decimals for whole numbers."""
    if digits == 0:
        return str(int(round(value)))
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


class PreferencesWindow(Adw.ApplicationWindow):
    def __init__(self, application, controller: Controller):
        super().__init__(application=application, title="Gattuccino", default_width=780, default_height=720)
        self.controller = controller
        self._pages = []
        self._dependent = []   # (field, widgets): shown only while the switch they depend on is on

        self.stack = Adw.ViewStack()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.ViewSwitcher(policy=Adw.ViewSwitcherPolicy.WIDE, stack=self.stack))
        self.apply_button = Gtk.Button(label="Apply")
        self.apply_button.connect("clicked", self.on_apply)
        header.pack_end(self.apply_button)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self.stack)
        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        self.build()
        self.connect("notify::is-active", self.on_active)

    # --- Building ---------------------------------------------------------

    def build(self):
        for page in self._pages:
            self.stack.remove(page)
        self._pages = []
        self._dependent = []

        for group_name, names in prefs.GROUPS:
            page = Adw.PreferencesPage()
            group = Adw.PreferencesGroup()
            page.add(group)
            for field in (f for f in self.controller.fields if f.group == group_name):
                widgets = self.rows_for(field)
                for widget in widgets:
                    group.add(widget)
                if field.requires:
                    self._dependent.append((field, widgets))
            self.stack.add_titled_with_icon(page, group_name, group_name, ICONS.get(group_name, "emblem-system-symbolic"))
            self._pages.append(page)
        self.sync()

    def rows_for(self, field: prefs.Field) -> list:
        """The widgets of a preference: one row, or two when a number may be a word instead."""
        if field.kind == prefs.SWITCH:
            return [self.switch_row(field)]
        if field.kind == prefs.CHOICE:
            return [self.choice_row(field)]
        if field.number and field.words:
            return self.number_or_word_rows(field)
        if field.number:
            return [self.number_row(field)]
        return [self.entry_row(field)]

    def _title(self, row, field):
        row.set_title(field.label)
        row.set_subtitle(field.spec.help)
        if field.live:
            tag = Gtk.Label(label="live", valign=Gtk.Align.CENTER)
            tag.add_css_class("dim-label")
            tag.add_css_class("caption")
            tag.set_tooltip_text("Takes effect at once, with no Apply")
            row.add_suffix(tag)

    def switch_row(self, field):
        row = Adw.SwitchRow()
        self._title(row, field)
        row.set_active(bool(getattr(self.controller.preferences, field.name)))
        row.connect("notify::active", lambda r, _p: self.change(field, row, "yes" if r.get_active() else "no"))
        return row

    def choice_row(self, field):
        row = Adw.ComboRow(model=Gtk.StringList.new(list(field.choices)))
        self._title(row, field)
        current = self.controller.text(field.name)
        row.set_selected(field.choices.index(current) if current in field.choices else 0)
        row.connect("notify::selected", lambda r, _p: self.change(field, row, field.choices[r.get_selected()]))
        return row

    def _spin(self, field, value):
        minimum, maximum, step, digits = field.number
        adjustment = Gtk.Adjustment(value=value, lower=minimum, upper=maximum, step_increment=step,
                                    page_increment=step * 10)
        return Adw.SpinRow(adjustment=adjustment, digits=digits)

    def number_row(self, field):
        _, _, _, digits = field.number
        row = self._spin(field, float(self.controller.text(field.name)))
        self._title(row, field)
        row.connect("notify::value", lambda r, _p: self.change(field, row, number_text(r.get_value(), digits)))
        return row

    def number_or_word_rows(self, field):
        """A word (round, dock, same) or a number of pixels or a fraction: a choice, and the number for the last."""
        _, _, _, digits = field.number
        words = list(field.words)
        text = self.controller.text(field.name)
        choice = Adw.ComboRow(model=Gtk.StringList.new([WORDS.get(w, w) for w in words] + [CUSTOM]))
        self._title(choice, field)
        spin = self._spin(field, float(text) if text not in words else field.number[0])
        spin.set_title(f"{field.label}, custom")
        spin.set_visible(text not in words)
        choice.set_selected(words.index(text) if text in words else len(words))

        def chosen(_row, _param):
            index = choice.get_selected()
            custom = index >= len(words)
            spin.set_visible(custom)
            self.change(field, choice, number_text(spin.get_value(), digits) if custom else words[index])

        choice.connect("notify::selected", chosen)
        spin.connect("notify::value", lambda r, _p: self.change(field, spin, number_text(r.get_value(), digits)))
        return [choice, spin]

    def entry_row(self, field):
        row = Adw.EntryRow(title=field.label, show_apply_button=True)
        text = self.controller.text(field.name)
        row.set_text("" if text == prefs.ICON_DEFAULT else text)
        row.set_tooltip_text(field.spec.help)
        row.connect("apply", lambda r: self.change(field, row, r.get_text().strip() or (
            prefs.ICON_DEFAULT if field.kind == prefs.FILE else "")))
        if field.live:
            tag = Gtk.Label(label="live", valign=Gtk.Align.CENTER)
            tag.add_css_class("dim-label")
            tag.add_css_class("caption")
            row.add_suffix(tag)
        if field.kind == prefs.FILE:
            choose = Gtk.Button(icon_name="document-open-symbolic", valign=Gtk.Align.CENTER,
                                tooltip_text="Choose a file")
            choose.add_css_class("flat")
            choose.connect("clicked", lambda _b: self.choose_file(field, row))
            row.add_suffix(choose)
        return row

    # --- Changing ---------------------------------------------------------

    def change(self, field, row, text):
        error = self.controller.set(field.name, text)
        if error:
            row.add_css_class("error")
            self.toasts.add_toast(Adw.Toast(title=error))
        else:
            row.remove_css_class("error")
        self.sync()

    def sync(self):
        """What depends on a switch is shown only while it is on, and Apply is there when it is wanted."""
        for field, widgets in self._dependent:
            for widget in widgets:
                widget.set_visible(self.controller.visible(field))
        pending = self.controller.pending
        self.apply_button.set_sensitive(bool(pending))
        self.apply_button.set_label(f"Apply ({len(pending)})" if pending else "Apply")
        if pending:
            self.apply_button.add_css_class("suggested-action")
        else:
            self.apply_button.remove_css_class("suggested-action")

    def choose_file(self, field, row):
        dialog = Gtk.FileDialog(title=field.label)
        images = Gtk.FileFilter(name="Images")
        images.add_mime_type("image/svg+xml")
        images.add_mime_type("image/png")
        dialog.set_filters(gi_list_store(Gtk.FileFilter, [images]))

        def chosen(source, result):
            try:
                path = source.open_finish(result).get_path()
            except GLib.Error:
                return   # closed without choosing
            row.set_text(path)
            self.change(field, row, path)

        dialog.open(self, None, chosen)

    def on_active(self, _window, _param):
        """Back in front: the extensions' own windows may have changed what they show."""
        if self.is_active() and self.controller.refresh():
            self.build()

    # --- Applying ---------------------------------------------------------

    def on_apply(self, _button):
        log = Gtk.TextView(editable=False, monospace=True, cursor_visible=False, left_margin=12, right_margin=12,
                           top_margin=8, bottom_margin=8)
        scroll = Gtk.ScrolledWindow(child=log, vexpand=True, min_content_height=240)
        spinner = Gtk.Spinner(spinning=True)
        close = Gtk.Button(label="Close", sensitive=False)
        close.add_css_class("suggested-action")
        bar = Gtk.Box(spacing=12, halign=Gtk.Align.END)
        bar.append(spinner)
        bar.append(close)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12,
                      margin_start=12, margin_end=12)
        box.append(scroll)
        box.append(bar)

        dialog = Adw.Dialog(title="Applying", child=box, content_width=600, content_height=420, can_close=False)
        close.connect("clicked", lambda _b: dialog.force_close())

        def add(line):
            end = log.get_buffer().get_end_iter()
            log.get_buffer().insert(end, line + "\n")
            return False

        def finish(error):
            spinner.set_spinning(False)
            close.set_sensitive(True)
            dialog.set_can_close(True)
            if error:
                add(f"\nFailed: {error}")
            else:
                add("\nDone.")
            self.sync()
            return False

        def work():
            try:
                self.controller.apply(log=lambda line: GLib.idle_add(add, str(line)))
            except ERRORS as e:
                GLib.idle_add(finish, str(e))
            except Exception as e:   # whatever it was, the person is told, and the window does not hang
                GLib.idle_add(finish, f"{type(e).__name__}: {e}")
            else:
                GLib.idle_add(finish, None)

        dialog.present(self)
        threading.Thread(target=work, daemon=True).start()


def gi_list_store(item_type, items):
    store = Gio.ListStore(item_type=item_type)
    for item in items:
        store.append(item)
    return store


class Application(Adw.Application):
    def __init__(self, desktop: Desktop = None, flags=Gio.ApplicationFlags.DEFAULT_FLAGS):
        super().__init__(application_id=APP_ID, flags=flags)
        self.desktop = desktop or Desktop()

    def do_activate(self):
        window = self.props.active_window
        if window is None:
            window = PreferencesWindow(self, Controller(self.desktop))
        window.present()


def run(argv=None) -> int:
    return Application().run(argv or [])
