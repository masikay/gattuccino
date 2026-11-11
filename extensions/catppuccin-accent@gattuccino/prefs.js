import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

const DOCK = 0, ROUND = 1, CUSTOM = 2;

// The dock of Dash to Dock, as settings of the extension: it dresses the dock
// while it runs, so a change here is seen at once.
export default class AccentPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage({title: 'Dock', icon_name: 'preferences-desktop-appearance-symbolic'});
        window.add(page);
        const group = new Adw.PreferencesGroup({
            title: 'Dash to Dock',
            description: 'How the dock looks, with Dash to Dock or Ubuntu Dock.',
        });
        page.add(group);

        // The corners: Dash to Dock's own, a pill, or a number of pixels
        const shape = new Adw.ComboRow({
            title: 'Corners',
            subtitle: "A round dock is given room at its ends, so that the first and the last icon clear the curve.",
            model: Gtk.StringList.new(["Dash to Dock's own", 'Round', 'Custom']),
        });
        const radius = new Adw.SpinRow({
            title: 'Corner radius',
            subtitle: 'In pixels.',
            adjustment: new Gtk.Adjustment({lower: 0, upper: 100, step_increment: 1, page_increment: 10}),
        });
        group.add(shape);
        group.add(radius);

        let updating = false;
        const show = () => {
            updating = true;
            const value = settings.get_string('dock-radius');
            shape.selected = value === 'dock' ? DOCK : value === 'round' ? ROUND : CUSTOM;
            radius.visible = shape.selected === CUSTOM;
            if (shape.selected === CUSTOM)
                radius.value = parseInt(value, 10) || 0;
            updating = false;
        };
        const write = () => {
            if (updating)
                return;
            const choice = shape.selected;
            settings.set_string('dock-radius',
                choice === DOCK ? 'dock' : choice === ROUND ? 'round' : String(Math.round(radius.value)));
        };
        shape.connect('notify::selected', write);
        radius.connect('notify::value', write);
        settings.connect('changed::dock-radius', show);
        show();

        // The icon of the Show Applications button
        const icon = new Adw.EntryRow({title: 'Show Applications icon'});
        icon.text = settings.get_string('show-apps-icon');
        icon.connect('apply', () => settings.set_string('show-apps-icon', icon.text.trim()));
        icon.show_apply_button = true;
        const choose = new Gtk.Button({icon_name: 'document-open-symbolic', valign: Gtk.Align.CENTER, tooltip_text: 'Choose a file'});
        choose.add_css_class('flat');
        choose.connect('clicked', () => this._chooseIcon(window, settings, icon));
        icon.add_suffix(choose);
        settings.connect('changed::show-apps-icon', () => {
            if (icon.text !== settings.get_string('show-apps-icon'))
                icon.text = settings.get_string('show-apps-icon');
        });
        group.add(icon);

        const note = new Adw.ActionRow({
            title: 'An .svg or .png file',
            subtitle: 'Leave it empty for the icon GNOME draws. {flavor} in the name stands for the flavor in use: ' +
                'icons/show-apps-{flavor}.svg is the icon of Latte in the light style and of the dark flavor in the dark one.',
        });
        note.add_css_class('dim-label');
        group.add(note);

        page.add(this._more());
    }

    _chooseIcon(window, settings, entry) {
        const dialog = new Gtk.FileDialog({title: 'Show Applications icon'});
        const filter = new Gtk.FileFilter({name: 'Images'});
        filter.add_mime_type('image/svg+xml');
        filter.add_mime_type('image/png');
        const filters = new Gio.ListStore({item_type: Gtk.FileFilter});
        filters.append(filter);
        dialog.filters = filters;
        dialog.open(window, null, (_dialog, result) => {
            try {
                const path = dialog.open_finish(result).get_path();
                entry.text = path;
                settings.set_string('show-apps-icon', path);
            } catch (e) {
                // closed without choosing
            }
        });
    }

    // What is built into the theme and not changed while it runs is in the
    // Gattuccino window, or `gattuccino configure`
    _more() {
        const group = new Adw.PreferencesGroup();
        const row = new Adw.ActionRow({
            title: 'More settings',
            subtitle: 'The colors, the opacities and what is installed are in the Gattuccino window.',
        });
        const button = new Gtk.Button({label: 'Open Gattuccino', valign: Gtk.Align.CENTER});
        button.connect('clicked', () => {
            openGattuccino();
        });
        row.add_suffix(button);
        group.add(row);
        return group;
    }
}

// The window is a launcher in the app grid, put there by `gattuccino apply`
function openGattuccino() {
    try {
        const app = Gio.DesktopAppInfo.new('org.gattuccino.Preferences.desktop');
        if (!app)
            throw new Error('it is not installed: run `gattuccino apply`');
        app.launch([], null);
    } catch (e) {
        console.warn(`gattuccino: could not open the window: ${e.message}`);
    }
}
