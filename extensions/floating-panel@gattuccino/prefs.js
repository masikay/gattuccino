import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

// The gap around the floating bar and how round it is, as settings of the
// extension: it reads them while it runs, so a change is seen at once.
export default class FloatingPanelPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage({title: 'Floating bar', icon_name: 'preferences-desktop-appearance-symbolic'});
        window.add(page);
        const group = new Adw.PreferencesGroup({
            title: 'Shape',
            description: 'How the top bar looks while it floats. It docks, with no gap, when a window comes close.',
        });
        page.add(group);

        const gap = new Adw.SpinRow({
            title: 'Gap',
            subtitle: 'Around the floating bar, in pixels.',
            adjustment: new Gtk.Adjustment({lower: 0, upper: 12, step_increment: 1}),
        });
        settings.bind('gap', gap, 'value', Gio.SettingsBindFlags.DEFAULT);
        group.add(gap);

        // The radius is the word 'round', or a number of pixels
        const round = new Adw.SwitchRow({title: 'Fully round', subtitle: 'A pill, as round as it can be.'});
        const radius = new Adw.SpinRow({
            title: 'Corner radius',
            subtitle: 'In pixels.',
            adjustment: new Gtk.Adjustment({lower: 0, upper: 100, step_increment: 1, page_increment: 10}),
        });
        group.add(round);
        group.add(radius);

        let updating = false;
        const show = () => {
            updating = true;
            const value = settings.get_string('radius');
            round.active = value === 'round';
            radius.sensitive = value !== 'round';
            if (value !== 'round')
                radius.value = parseInt(value, 10) || 0;
            updating = false;
        };
        const write = () => {
            if (!updating)
                settings.set_string('radius', round.active ? 'round' : String(Math.round(radius.value)));
        };
        round.connect('notify::active', write);
        radius.connect('notify::value', write);
        settings.connect('changed::radius', show);
        show();

        // What is built into the theme and not changed while it runs is in the
        // Gattuccino window, or `gattuccino configure`
        const more = new Adw.PreferencesGroup();
        const row = new Adw.ActionRow({
            title: 'More settings',
            subtitle: 'The colors, the opacities and what is installed are in the Gattuccino window.',
        });
        const button = new Gtk.Button({label: 'Open Gattuccino', valign: Gtk.Align.CENTER});
        button.connect('clicked', () => openGattuccino());
        row.add_suffix(button);
        more.add(row);
        page.add(more);
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
