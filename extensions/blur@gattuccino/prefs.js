import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

// How far to blur, as settings of the extension: it reads them while it runs,
// so a change here is seen at once.
export default class BlurPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage({title: 'Blur', icon_name: 'preferences-desktop-appearance-symbolic'});
        window.add(page);

        const surfaces = new Adw.PreferencesGroup({
            title: 'Surfaces',
            description: 'What is blurred behind the top bar, the popup menus and the dock, when they are translucent.',
        });
        page.add(surfaces);
        surfaces.add(spinRow(settings, 'radius', 'Blur radius', 'How far the blur reaches, in pixels. 0 turns it off.'));

        const wallpaper = new Adw.PreferencesGroup({
            title: 'Wallpaper',
            description: 'The wallpaper behind the overview and on the lock screen.',
        });
        page.add(wallpaper);
        const blurred = new Adw.SwitchRow({title: 'Blur the wallpaper'});
        settings.bind('background', blurred, 'active', Gio.SettingsBindFlags.DEFAULT);
        wallpaper.add(blurred);
        const radius = spinRow(settings, 'background-radius', 'Wallpaper blur radius',
            'How far the blur of the wallpaper reaches, in pixels.');
        settings.bind('background', radius, 'sensitive', Gio.SettingsBindFlags.GET);
        wallpaper.add(radius);

        page.add(moreSettings());
    }
}

function spinRow(settings, key, title, subtitle, upper = 100) {
    const row = new Adw.SpinRow({
        title,
        subtitle,
        adjustment: new Gtk.Adjustment({lower: 0, upper, step_increment: 1, page_increment: 10}),
    });
    settings.bind(key, row, 'value', Gio.SettingsBindFlags.DEFAULT);
    return row;
}

// What is built into the theme and not changed while it runs is in the
// Gattuccino window, or `gattuccino configure`
function moreSettings() {
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
