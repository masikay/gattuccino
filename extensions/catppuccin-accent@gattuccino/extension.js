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
//   rules the theme in use was built with, if it has them;
// - the dock of Dash to Dock, as its own settings say while this runs
//   (dock-radius, and show-apps-icon: the icon of the flavor in use that comes
//   with the extension, GNOME's own, or a file of the person's, in which
//   {flavor} stands for the flavor in use): the corners of the dock, and the
//   icon of its Show Applications button, which follows the style as the
//   theme is switched;
// - the tools in a terminal (eza, ...): runs `gattuccino sync`, the command of
//   the sync-command setting, whenever the style or the accent changes, so that
//   they follow the flavor and the accent of the theme;
// - the lock screen: the same for gattuccino-lock.css. The Shell runs the
//   lock screen with its own stylesheet and not the theme's, so the accent
//   there is a stylesheet of an extension too, which this one keeps loaded
//   while the screen is locked as well.
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
const LOCK_STYLESHEET = 'gattuccino-lock.css';
const ACCENT_STYLESHEETS = [DOCK_STYLESHEET, LOCK_STYLESHEET];
const FLAVOR_OF_THEME = /^gattuccino-(latte|frappe|macchiato|mocha)-/;
const DOCK_CONTAINER = 'dashtodockContainer';
const SHOW_APPS_ICON_CLASS = 'show-apps-icon';
const DASH_BACKGROUND_CLASS = 'dash-background';

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
        this._dockIdleId = 0;
        this._toolsId = 0;
        // The settings of the dock, changed while this runs
        this._prefs = this.getSettings();
        this._prefsId = this._prefs.connect('changed', () => this._queueIcons());
        this._dressed = new Map();      // St.Icon -> what it was before
        this._shaped = new Map();       // the background of a dock -> the style it had
        this._watched = new Map();      // what is heard from -> the ids of what is heard
        this._iconIdleId = 0;
        this._uiGroupId = 0;
        // A dock that comes and goes, and one that is made again
        const uiGroup = Main.layoutManager?.uiGroup;
        if (uiGroup)
            this._uiGroupId = uiGroup.connect('child-added', () => this._queueIcons());

        this._changedIds = ['accent-color', 'color-scheme'].map(key =>
            this._interfaceSettings.connect(`changed::${key}`, () => this._sync()));
        // The dock stylesheet belongs to one theme: it follows whichever is
        // selected, and GNOME Shell replaces the St theme whenever the theme
        // changes, which drops the stylesheets loaded into it.
        this._themeContext = St.ThemeContext.get_for_stage(global.stage);
        this._themeChangedId = this._themeContext.connect('changed', () => this._queueDock());
        this._themeNameChangedId = this._userThemeSettings?.connect(
            'changed::name', () => this._queueDock()) ?? 0;
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
        if (this._dockIdleId) {
            GLib.source_remove(this._dockIdleId);
            this._dockIdleId = 0;
        }
        if (this._toolsId) {
            GLib.source_remove(this._toolsId);
            this._toolsId = 0;
        }
        this._unloadDock();
        this._unloadDockIcon();
        this._prefs.disconnect(this._prefsId);
        this._prefsId = 0;
        this._prefs = null;
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
        this._queueDock();
        this._queueTools();
    }

    // The tools in a terminal are themed by `gattuccino sync`, which reads the
    // style and the accent for itself. It is asked once for however many changes
    // there are in a moment: the accent and the style are often changed together.
    _queueTools() {
        if (this._toolsId)
            return;
        this._toolsId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
            this._toolsId = 0;
            this._runSync();
            return GLib.SOURCE_REMOVE;
        });
    }

    _runSync() {
        const command = this._prefs?.get_string('sync-command');
        if (!command)
            return;
        try {
            Gio.Subprocess.new([command, 'sync'],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch (e) {
            console.warn(`${this.uuid}: could not run ${command} sync: ${e.message}`);
        }
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

    // Loading a stylesheet into the theme makes St emit `changed` on the theme
    // context, and that is the signal asking for the stylesheet in the first
    // place: syncing inline re-enters _syncDock() from inside load_stylesheet().
    // Unlocking the screen sets off a flurry of theme changes, and that nesting
    // used to recurse until it exhausted the JS stack. An idle call breaks the
    // nesting, and collapses the flurry into a single update.
    _queueDock() {
        if (this._dockIdleId)
            return;

        this._dockIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._dockIdleId = 0;
            this._syncDock();
            return GLib.SOURCE_REMOVE;
        });
    }

    // Loads the accent rules for the dock and for the lock screen that come
    // with the selected theme, and drops the ones loaded for another theme.
    // Themes that are not ours, and ours built without accent-selection, have
    // no such files: nothing is then loaded, and the dock keeps the colors of
    // Dash to Dock and the lock screen those of GNOME.
    _syncDock() {
        const theme = this._themeContext?.get_theme();
        const name = this._userThemeSettings?.get_string('name');
        // A theme that is not ours, or another flavor: the icon of its own
        this._queueIcons();
        const files = name?.match(VARIANT_NAME)
            ? ACCENT_STYLESHEETS.map(basename => this._themeFile(name, basename)).filter(file => file)
            : [];

        const [loadedTheme, loadedFiles] = this._dockStylesheet ?? [];
        if (loadedTheme === theme && files.length &&
            files.length === loadedFiles.length && files.every((file, i) => loadedFiles[i].equal(file)))
            return;

        this._unloadDock();
        if (!theme || !files.length)
            return;
        // Recorded before loading: load_stylesheet() can come straight back
        // here, and the check above is what has to stop it
        this._dockStylesheet = [theme, files];
        for (const file of files) {
            try {
                theme.load_stylesheet(file);
            } catch (e) {
                console.warn(`${this.uuid}: could not load ${file.get_path()}: ${e.message}`);
            }
        }
    }

    _unloadDock() {
        if (!this._dockStylesheet)
            return;
        const [theme, files] = this._dockStylesheet;
        this._dockStylesheet = null;
        for (const file of files) {
            try {
                theme.unload_stylesheet(file);
            } catch (e) {
                console.warn(`${this.uuid}: could not unload ${file.get_path()}: ${e.message}`);
            }
        }
    }

    // The dock is dressed from its own settings: the icon of the Show
    // Applications button, and the corners of the background. It is done on
    // the actors, and not with a stylesheet or the icon folder, so that a
    // change of the settings is seen at once: the Shell has read the icons by
    // then, and a stylesheet outranks what is set on an actor only by being
    // !important, which would leave the settings nothing to say.
    _queueIcons() {
        if (this._iconIdleId)
            return;
        this._iconIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._iconIdleId = 0;
            this._dressDock();
            return GLib.SOURCE_REMOVE;
        });
    }

    // The icon file of the flavor in use, if there is one: the one that comes
    // with the extension unless the setting says otherwise, or none when it says
    // 'gnome', and a file of the person's own, which may have {flavor} in its name
    _iconFile() {
        const setting = this._prefs.get_string('show-apps-icon');
        if (setting === 'gnome')
            return null;
        const pattern = setting || GLib.build_filenamev([this.path, 'icons', 'show-apps-{flavor}.svg']);
        const name = this._userThemeSettings?.get_string('name') ?? '';
        const flavor = name.match(FLAVOR_OF_THEME)?.[1] ?? 'mocha';
        const file = Gio.File.new_for_path(pattern.replace('{flavor}', flavor));
        return file.query_exists(null) ? file : null;
    }

    // The corners of the background of a dock, and the room at its ends that
    // the first and the last icon need to clear the curve: an icon tile in a
    // pill about 60px tall needs some 12px at each end, and a little more to
    // breathe. The curve a number of pixels draws is shallower, and needs less.
    // Nothing for a dock that is extended over the whole edge, which is a
    // panel and stays square, or when the setting leaves Dash to Dock's own.
    _shapeStyle(container) {
        const setting = this._prefs.get_string('dock-radius');
        if (setting === 'dock' || container.has_style_class_name?.('extended'))
            return null;
        const radius = setting === 'round' ? 999 : parseInt(setting, 10);
        if (!Number.isFinite(radius))
            return null;
        const pad = setting === 'round' ? 15 : Math.floor((Math.min(radius, 30) + 1) / 2);
        const vertical = ['left', 'right'].some(edge => container.has_style_class_name?.(edge));
        const [a, b] = vertical ? ['top', 'bottom'] : ['left', 'right'];
        return `border-radius: ${radius}px; padding-${a}: ${pad}px; padding-${b}: ${pad}px;`;
    }

    // The buttons are made again whenever the dock changes the size of its
    // icons, and each time they come without the icon: it is heard from the
    // actor that holds them. A dock that changes its edge or is extended is
    // heard from too.
    _dressDock() {
        const docks = this._findDocks();
        const file = this._iconFile();
        const icons = docks.flatMap(dock => dock.icons);

        if (file) {
            for (const icon of icons)
                this._dressIcon(icon, file);
            // The ones that were made again are gone, and need nothing put back
            for (const icon of [...this._dressed.keys()]) {
                if (!icons.includes(icon))
                    this._dressed.delete(icon);
            }
        } else {
            for (const [icon, before] of this._dressed)
                this._restoreIcon(icon, before);
            this._dressed.clear();
        }

        const backgrounds = [];
        for (const {container, backgrounds: found} of docks) {
            this._watch(container, 'style-changed');
            const style = this._shapeStyle(container);
            for (const background of found) {
                backgrounds.push(background);
                if (style)
                    this._shape(background, style);
                else
                    this._unshape(background);
            }
        }
        for (const background of [...this._shaped.keys()]) {
            if (!backgrounds.includes(background))
                this._shaped.delete(background);
        }
    }

    _findDocks() {
        const docks = [];
        const uiGroup = Main.layoutManager?.uiGroup;
        for (const container of (uiGroup?.get_children() ?? []).filter(actor => actor.name === DOCK_CONTAINER)) {
            const dock = {container, icons: [], backgrounds: []};
            const stack = [container];
            while (stack.length) {
                const actor = stack.pop();
                if (actor.has_style_class_name?.(SHOW_APPS_ICON_CLASS))
                    dock.icons.push(actor);
                if (actor.has_style_class_name?.(DASH_BACKGROUND_CLASS))
                    dock.backgrounds.push(actor);
                stack.push(...actor.get_children());
            }
            docks.push(dock);
        }
        return docks;
    }

    // Heard from once, whatever number of times it is asked for
    _watch(actor, ...signals) {
        if (this._watched.has(actor))
            return;
        const ids = signals.map(signal => actor.connect(signal, () => this._queueIcons()));
        ids.push(actor.connect('destroy', () => this._watched.delete(actor)));
        this._watched.set(actor, ids);
    }

    _shape(background, style) {
        if (!this._shaped.has(background))
            this._shaped.set(background, background.style ?? '');
        if (background.style !== style)
            background.style = style;
    }

    _unshape(background) {
        if (!this._shaped.has(background))
            return;
        background.style = this._shaped.get(background);
        this._shaped.delete(background);
    }

    _dressIcon(icon, file) {
        // Heard from the actor that holds it, which keeps the same icon only
        // until the dock makes it again
        const parent = icon.get_parent();
        if (parent)
            this._watch(parent, 'notify::child');
        if (!this._dressed.has(icon))
            this._dressed.set(icon, {name: icon.icon_name, gicon: icon.gicon, style: icon.style ?? ''});
        // A name ending in -symbolic is taken to mean a one-color icon, which
        // the Shell paints in the color of the text; this is a picture
        if (icon.style !== '-st-icon-style: regular;')
            icon.style = '-st-icon-style: regular;';
        if (icon.gicon?.get_file?.().equal(file))
            return;
        icon.gicon = new Gio.FileIcon({file});
    }

    _restoreIcon(icon, before) {
        try {
            icon.style = before.style;
            if (before.name)
                icon.icon_name = before.name;
            else
                icon.gicon = before.gicon;
        } catch (e) {
            // the button has gone, and its icon with it
        }
    }

    _unloadDockIcon() {
        if (this._iconIdleId) {
            GLib.source_remove(this._iconIdleId);
            this._iconIdleId = 0;
        }
        if (this._uiGroupId)
            Main.layoutManager.uiGroup.disconnect(this._uiGroupId);
        this._uiGroupId = 0;
        for (const [actor, ids] of this._watched) {
            for (const id of ids) {
                try {
                    actor.disconnect(id);
                } catch (e) {
                    // gone with the dock
                }
            }
        }
        this._watched.clear();
        for (const [icon, before] of this._dressed)
            this._restoreIcon(icon, before);
        this._dressed.clear();
        for (const [background, style] of this._shaped) {
            try {
                background.style = style;
            } catch (e) {
                // gone with the dock
            }
        }
        this._shaped.clear();
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
