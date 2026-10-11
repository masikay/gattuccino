import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// Makes the style (light or dark) and the accent color picked in Settings >
// Appearance apply as their Catppuccin counterparts: Latte for the light style,
// the chosen dark flavor for the dark one, and for each of GNOME's nine accents
// a Catppuccin accent (when the accent follows Settings):
//
// - GNOME Shell: switches the User Themes extension to the variant of the
//   current theme built for that flavor and accent, e.g. from
//   gattuccino-mocha-teal to gattuccino-latte-mauve;
// - applications: rewrites gtk.css (which flavor it imports) and
//   gattuccino-accent.css in ~/.config/gtk-4.0 and ~/.config/gtk-3.0,
//   and switches GTK 3 between adw-gtk3 and adw-gtk3-dark;
// - the dock of Dash to Dock: loads gattuccino-dock.css, the accent
//   rules the theme in use was built with, if it has them.
//
// It only touches what belongs to Gattuccino: a shell theme whose name
// does not end in one of the accents below is left alone, and so are GTK
// files that this project did not write.

// Accent picked in Settings -> Catppuccin accent standing in for it.
// Keep in sync with SETTINGS_ACCENTS in src/gattuccino/palette.py.
const ACCENT_NAMES = {
    blue: 'blue', teal: 'teal', green: 'green', yellow: 'yellow', orange: 'peach',
    red: 'red', pink: 'pink', purple: 'mauve', slate: 'lavender',
};

// The 14 accents of each flavor, with the color of what sits on them (base).
// Keep in sync with FLAVORS in src/gattuccino/palette.py.
const FLAVORS = {
    latte: {
        base: '#eff1f5',
        rosewater: '#dc8a78', flamingo: '#dd7878', pink: '#ea76cb', mauve: '#8839ef',
        red: '#d20f39', maroon: '#e64553', peach: '#fe640b', yellow: '#df8e1d',
        green: '#40a02b', teal: '#179299', sky: '#04a5e5', sapphire: '#209fb5',
        blue: '#1e66f5', lavender: '#7287fd',
    },
    frappe: {
        base: '#303446',
        rosewater: '#f2d5cf', flamingo: '#eebebe', pink: '#f4b8e4', mauve: '#ca9ee6',
        red: '#e78284', maroon: '#ea999c', peach: '#ef9f76', yellow: '#e5c890',
        green: '#a6d189', teal: '#81c8be', sky: '#99d1db', sapphire: '#85c1dc',
        blue: '#8caaee', lavender: '#babbf1',
    },
    macchiato: {
        base: '#24273a',
        rosewater: '#f4dbd6', flamingo: '#f0c6c6', pink: '#f5bde6', mauve: '#c6a0f6',
        red: '#ed8796', maroon: '#ee99a0', peach: '#f5a97f', yellow: '#eed49f',
        green: '#a6da95', teal: '#8bd5ca', sky: '#91d7e3', sapphire: '#7dc4e4',
        blue: '#8aadf4', lavender: '#b7bdf8',
    },
    mocha: {
        base: '#1e1e2e',
        rosewater: '#f5e0dc', flamingo: '#f2cdcd', pink: '#f5c2e7', mauve: '#cba6f7',
        red: '#f38ba8', maroon: '#eba0ac', peach: '#fab387', yellow: '#f9e2af',
        green: '#a6e3a1', teal: '#94e2d5', sky: '#89dceb', sapphire: '#74c7ec',
        blue: '#89b4fa', lavender: '#b4befe',
    },
};

const LIGHT_FLAVOR = 'latte';
const DARK_FLAVORS = Object.keys(FLAVORS).filter(flavor => flavor !== LIGHT_FLAVOR);

const ACCENTS = Object.keys(FLAVORS.latte).filter(name => name !== 'base');
const VARIANT_NAME = new RegExp(`^(.+)-(${ACCENTS.join('|')})$`);
const FLAVOR_NAME = new RegExp(`^(.+)-(${Object.keys(FLAVORS).join('|')})$`);

const USER_THEME_UUID = 'user-theme@gnome-shell-extensions.gcampax.github.com';
const USER_THEME_SCHEMA = 'org.gnome.shell.extensions.user-theme';

// The accent for the dock of Dash to Dock, written next to the stylesheet of
// a theme built with accent-selection on. It is loaded as an extension
// stylesheet, and not left to the theme, because Dash to Dock states those
// colors in its own stylesheet, which outranks every theme.
const DOCK_STYLESHEET = 'gattuccino-dock.css';

// Same places the User Themes extension loads shell themes from
function themeDirs() {
    return [
        GLib.build_filenamev([GLib.get_home_dir(), '.themes']),
        GLib.build_filenamev([GLib.get_user_data_dir(), 'themes']),
        ...GLib.get_system_data_dirs().map(dir => GLib.build_filenamev([dir, 'themes'])),
    ];
}

// gtk.css and the accent files, exactly as src/gattuccino/gtk_theme.py
// writes them. The first line marks a file as ours and tells what it is for.
// Either marker is read, so a file written by this project's old name,
// gnome-catppuccin, is still recognized.
const GTK_ACCENT_FILE = 'gattuccino-accent.css';
const GTK_STYLE = /^\/\* (?:gattuccino|gnome-catppuccin): style \(light=([a-z]+), dark=([a-z]+)\)\n/;
const GTK_ACCENT = /^\/\* (?:gattuccino|gnome-catppuccin): accent \(flavor=[a-z]+, accent=([a-z]+)\)\n/;

function gtkCss(light, dark, flavor) {
    return `/* gattuccino: style (light=${light}, dark=${dark})
 * Written by gattuccino, and by its Catppuccin Accent extension whenever
 * the style changes in Settings. Edits to this file are overwritten. */

@import url("gattuccino-${flavor}.css");
@import url("${GTK_ACCENT_FILE}");
`;
}

function gtkAccentHeader(flavor, setting) {
    return `/* gattuccino: accent (flavor=${flavor}, accent=${setting})
 * Written by gattuccino, and by its Catppuccin Accent extension whenever
 * the style or the accent color changes in Settings. Edits to this file are overwritten. */
`;
}

function gtkNamedColors(color, foreground) {
    return `@define-color accent_bg_color ${color};
@define-color accent_fg_color ${foreground};
@define-color accent_color ${color};
`;
}

function gtk4AccentCss(flavor, setting, color, foreground) {
    return `${gtkAccentHeader(flavor, setting)}
:root {
  --accent-bg-color: ${color};
  --accent-fg-color: ${foreground};
  --accent-color: ${color};
}

${gtkNamedColors(color, foreground)}`;
}

function gtk3AccentCss(flavor, setting, color, foreground) {
    return `${gtkAccentHeader(flavor, setting)}
${gtkNamedColors(color, foreground)}`;
}

const GTK_ACCENT_FILES = [
    ['gtk-4.0', gtk4AccentCss],
    ['gtk-3.0', gtk3AccentCss],
];

export default class CatppuccinAccentExtension extends Extension {
    enable() {
        this._interfaceSettings = new Gio.Settings({
            schema_id: 'org.gnome.desktop.interface',
        });
        this._userThemeSettings = this._getUserThemeSettings();
        this._dockStylesheet = null;

        this._changedIds = ['accent-color', 'color-scheme'].map(key =>
            this._interfaceSettings.connect(`changed::${key}`, () => this._sync()));
        // The dock stylesheet belongs to one theme: it follows whichever is
        // selected, and GNOME Shell replaces the St theme whenever the theme
        // changes, which drops the stylesheets loaded into it.
        this._themeContext = St.ThemeContext.get_for_stage(global.stage);
        this._themeChangedId = this._themeContext.connect('changed', () => this._syncDock());
        this._themeNameChangedId = this._userThemeSettings?.connect(
            'changed::name', () => this._syncDock()) ?? 0;
        this._sync();
    }

    // Nothing is reverted here, except the stylesheet, which is loaded into
    // the theme in use: extensions are also disabled every time the screen
    // locks.
    disable() {
        for (const id of this._changedIds)
            this._interfaceSettings.disconnect(id);
        this._changedIds = null;
        if (this._themeNameChangedId)
            this._userThemeSettings.disconnect(this._themeNameChangedId);
        this._themeNameChangedId = 0;
        this._themeContext.disconnect(this._themeChangedId);
        this._themeChangedId = 0;
        this._unloadDock();
        this._themeContext = null;
        this._interfaceSettings = null;
        this._userThemeSettings = null;
    }

    _sync() {
        // undefined for an accent this does not know: the accent is then kept
        const picked = ACCENT_NAMES[this._interfaceSettings.get_string('accent-color')];
        const dark = this._interfaceSettings.get_string('color-scheme') === 'prefer-dark';

        this._syncShellTheme(picked, dark);
        this._syncGtk(picked, dark);
        this._syncDock();
    }

    // The settings of the User Themes extension, found the way the extension
    // finds them itself; null if it is not installed.
    _getUserThemeSettings() {
        try {
            let source = Gio.SettingsSchemaSource.get_default();
            const schemaDir = Main.extensionManager.lookup(USER_THEME_UUID)
                ?.dir.get_child('schemas');
            if (schemaDir?.query_exists(null)) {
                source = Gio.SettingsSchemaSource.new_from_directory(
                    schemaDir.get_path(), source, false);
            }

            const schema = source.lookup(USER_THEME_SCHEMA, true);
            return schema ? new Gio.Settings({settings_schema: schema}) : null;
        } catch (e) {
            console.warn(`${this.uuid}: no User Themes settings: ${e.message}`);
            return null;
        }
    }

    // Theme names end in the flavor and the accent, e.g. gattuccino-mocha-teal.
    // Only installed variants are selected: the accent picked in Settings if
    // there is one for it (there is not when the accent is fixed), otherwise
    // the current accent; in the flavor of the style.
    _syncShellTheme(picked, dark) {
        if (!this._userThemeSettings)
            return;

        const current = this._userThemeSettings.get_string('name');
        const [, prefix, accent] = current.match(VARIANT_NAME) ?? [];
        if (!prefix)
            return;

        let prefixes = [prefix];
        const [, base, flavor] = prefix.match(FLAVOR_NAME) ?? [];
        if (base && !dark)
            prefixes = [`${base}-${LIGHT_FLAVOR}`];
        else if (base && flavor === LIGHT_FLAVOR)  // whichever dark flavor is installed
            prefixes = DARK_FLAVORS.map(f => `${base}-${f}`);

        for (const wanted of [picked, accent].filter(Boolean)) {
            for (const p of prefixes) {
                const variant = `${p}-${wanted}`;
                if (this._themeExists(variant)) {
                    if (variant !== current)
                        this._userThemeSettings.set_string('name', variant);
                    return;
                }
            }
        }
    }

    _themeExists(name) {
        return !!this._themeFile(name, 'gnome-shell.css');
    }

    // A file of an installed shell theme, or null if there is none
    _themeFile(name, basename) {
        for (const dir of themeDirs()) {
            const file = Gio.File.new_for_path(GLib.build_filenamev(
                [dir, name, 'gnome-shell', basename]));
            if (file.query_exists(null))
                return file;
        }
        return null;
    }

    // Loads the accent rules for the dock that come with the selected theme,
    // and drops the ones loaded for another theme. Themes that are not ours,
    // and ours built without accent-selection, have no such file: nothing is
    // then loaded, and the dock keeps the colors of Dash to Dock.
    _syncDock() {
        const theme = this._themeContext?.get_theme();
        const name = this._userThemeSettings?.get_string('name');
        const file = name?.match(VARIANT_NAME)
            ? this._themeFile(name, DOCK_STYLESHEET) : null;

        const [loadedTheme, loadedFile] = this._dockStylesheet ?? [];
        if (loadedTheme === theme && file && loadedFile?.equal(file))
            return;

        this._unloadDock();
        if (!theme || !file)
            return;
        try {
            theme.load_stylesheet(file);
            this._dockStylesheet = [theme, file];
        } catch (e) {
            console.warn(`${this.uuid}: could not load ${file.get_path()}: ${e.message}`);
        }
    }

    _unloadDock() {
        if (!this._dockStylesheet)
            return;
        const [theme, file] = this._dockStylesheet;
        this._dockStylesheet = null;
        try {
            theme.unload_stylesheet(file);
        } catch (e) {
            console.warn(`${this.uuid}: could not unload ${file.get_path()}: ${e.message}`);
        }
    }

    _syncGtk(picked, dark) {
        let styled = false;
        for (const [folder, css] of GTK_ACCENT_FILES) {
            // The flavor of the style, as gtk.css says which two there are
            const style = this._readGtkFile(folder, 'gtk.css')?.match(GTK_STYLE);
            if (!style || !FLAVORS[style[1]] || !FLAVORS[style[2]])
                continue;
            const flavor = dark ? style[2] : style[1];
            this._writeGtkFile(folder, 'gtk.css', gtkCss(style[1], style[2], flavor));
            styled ||= folder === 'gtk-3.0';

            // The accent: the one picked in Settings, or the fixed one
            const setting = this._readGtkFile(folder, GTK_ACCENT_FILE)?.match(GTK_ACCENT)?.[1];
            const accent = setting === 'follow' ? picked : setting;
            const colors = FLAVORS[flavor];
            if (accent && colors[accent]) {
                this._writeGtkFile(folder, GTK_ACCENT_FILE,
                    css(flavor, setting, colors[accent], colors.base));
            }
        }

        // GTK 3 applications follow through adw-gtk3, which has a theme per style
        if (styled) {
            const theme = this._interfaceSettings.get_string('gtk-theme');
            const wanted = dark ? 'adw-gtk3-dark' : 'adw-gtk3';
            if (['adw-gtk3', 'adw-gtk3-dark'].includes(theme) && theme !== wanted)
                this._interfaceSettings.set_string('gtk-theme', wanted);
        }
    }

    // Contents of a file in ~/.config/FOLDER, or null if it cannot be read
    _readGtkFile(folder, name) {
        const file = Gio.File.new_for_path(GLib.build_filenamev(
            [GLib.get_user_config_dir(), folder, name]));
        try {
            if (!file.query_exists(null))
                return null;
            const [, bytes] = file.load_contents(null);
            return new TextDecoder().decode(bytes);
        } catch (e) {
            console.warn(`${this.uuid}: could not read ${file.get_path()}: ${e.message}`);
            return null;
        }
    }

    // Only called for files that are there and ours; unchanged ones are not rewritten
    _writeGtkFile(folder, name, contents) {
        const file = Gio.File.new_for_path(GLib.build_filenamev(
            [GLib.get_user_config_dir(), folder, name]));
        try {
            const [, bytes] = file.load_contents(null);
            if (new TextDecoder().decode(bytes) === contents)
                return;
            file.replace_contents(new TextEncoder().encode(contents),
                null, false, Gio.FileCreateFlags.NONE, null);
        } catch (e) {
            console.warn(`${this.uuid}: could not update ${file.get_path()}: ${e.message}`);
        }
    }
}
