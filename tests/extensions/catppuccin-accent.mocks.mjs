// Stand-ins for the parts of GNOME Shell and GLib the catppuccin-accent
// extension uses: settings, files (kept in memory), the extension manager and
// the St theme stylesheets are loaded into.
export const files = new Map();     // path -> contents
export const written = [];          // paths written, in order
export const settings = {
    'org.gnome.desktop.interface': {'accent-color': 'blue', 'color-scheme': 'prefer-dark', 'gtk-theme': 'Adwaita'},
    'org.gnome.shell.extensions.user-theme': {name: ''},
};
// userThemes: 'user' (from extensions.gnome.org), 'system' (packaged) or false
export const environment = {userThemes: 'user', failWrites: false, failLoads: false};

const USER_THEME_UUID = 'user-theme@gnome-shell-extensions.gcampax.github.com';
export const USER_THEME_DIR = `/home/u/.local/share/gnome-shell/extensions/${USER_THEME_UUID}`;

const handlers = new Map();
let handlerNext = 0;
function emitSignal(owner, signal) {
    for (const [o, s, callback] of [...handlers.values()])
        if (o === owner && s === signal) callback();
}
function emit(schema, key) { emitSignal(schema, `changed::${key}`); }
export const handlerCount = () => handlers.size;
export function pickAccent(name) {
    settings['org.gnome.desktop.interface']['accent-color'] = name;
    emit('org.gnome.desktop.interface', 'accent-color');
}
// 'default' (light), 'prefer-dark' or 'prefer-light', as Settings > Appearance sets it
export function pickStyle(scheme) {
    settings['org.gnome.desktop.interface']['color-scheme'] = scheme;
    emit('org.gnome.desktop.interface', 'color-scheme');
}
// A shell theme selected from somewhere else, the installer for instance
export function switchTheme(name) {
    settings['org.gnome.shell.extensions.user-theme'].name = name;
    emit('org.gnome.shell.extensions.user-theme', 'name');
}

class Settings {
    constructor(properties) {
        this.schema = properties.schema_id ?? properties.settings_schema.id;
        if (!settings[this.schema]) throw new Error(`no schema ${this.schema}`);
    }
    get_string(key) { return settings[this.schema][key]; }
    set_string(key, value) {
        if (settings[this.schema][key] === value) return;
        settings[this.schema][key] = value;
        emit(this.schema, key);
    }
    connect(signal, callback) { const id = ++handlerNext; handlers.set(id, [this.schema, signal, callback]); return id; }
    disconnect(id) { if (!handlers.delete(id)) throw new Error('unknown handler'); }
}

class File {
    constructor(path) { this.path = path; }
    static new_for_path(path) { return new File(path); }
    get_path() { return this.path; }
    equal(other) { return other instanceof File && other.path === this.path; }
    get_child(name) { return new File(`${this.path}/${name}`); }
    query_exists() { return files.has(this.path) || [...files.keys()].some(p => p.startsWith(`${this.path}/`)); }
    load_contents() {
        if (!files.has(this.path)) throw new Error('No such file');
        return [true, new TextEncoder().encode(files.get(this.path))];
    }
    replace_contents(bytes) {
        if (environment.failWrites) throw new Error('Read-only file system');
        files.set(this.path, new TextDecoder().decode(bytes));
        written.push(this.path);
        return [true, null];
    }
}

const source = hasUserThemes => ({
    lookup: id => id === 'org.gnome.shell.extensions.user-theme' && hasUserThemes ? {id} : null,
});
export const Gio = {
    Settings, File, FileCreateFlags: {NONE: 0},
    SettingsSchemaSource: {
        get_default: () => source(environment.userThemes === 'system'),
        new_from_directory(path) {
            if (!files.has(`${path}/gschemas.compiled`)) throw new Error('no compiled schemas');
            return source(true);
        },
    },
};
export const GLib = {
    PRIORITY_DEFAULT: 0,
    SOURCE_REMOVE: false,
    idle_add(_priority, callback) { const id = ++idleNext; idle.set(id, callback); return id; },
    source_remove(id) { if (!idle.delete(id)) throw new Error('unknown source'); },
    build_filenamev: parts => parts.join('/'),
    get_home_dir: () => '/home/u',
    get_user_data_dir: () => '/home/u/.local/share',
    get_system_data_dirs: () => ['/usr/local/share', '/usr/share'],
    get_user_config_dir: () => '/home/u/.config',
};
export const Main = {
    extensionManager: {
        lookup: uuid => uuid === USER_THEME_UUID && environment.userThemes === 'user'
            ? {dir: new File(USER_THEME_DIR)} : undefined,
    },
};
export class Extension { get uuid() { return 'catppuccin-accent@gattuccino'; } }

// The St theme: GNOME Shell makes a new one whenever the shell theme changes,
// which drops the stylesheets that were loaded into it.
// Idle calls, run by settle() below. Loading a stylesheet makes the shell
// restyle, so the extension defers it; a test sees the result after settling.
const idle = new Map();
let idleNext = 0;
export const pendingIdle = () => idle.size;

// Runs queued idle calls until none is left, which is what the shell does
// between frames. Guarded: a bug that queues work from its own idle call
// would otherwise hang the test run instead of failing it.
export function settle(limit = 100) {
    for (let round = 0; idle.size; round++) {
        if (round >= limit)
            throw new Error(`idle calls still queued after ${limit} rounds: not settling`);
        for (const [id, callback] of [...idle]) {
            idle.delete(id);
            callback();
        }
    }
}

const THEME_CONTEXT = 'St.ThemeContext';
class Theme {
    constructor() { this.stylesheets = new Set(); }
    load_stylesheet(file) {
        if (environment.failLoads) throw new Error('could not be parsed');
        loads++;
        const known = this.stylesheets.has(file.get_path());
        this.stylesheets.add(file.get_path());
        // As the real St does: the theme changed, so the context says so, and
        // it says so from inside this call
        if (!known)
            emitSignal(THEME_CONTEXT, 'changed');
    }
    unload_stylesheet(file) { this.stylesheets.delete(file.get_path()); }
}
let theme = new Theme();
export const loaded = () => [...theme.stylesheets];

// How many times a stylesheet was loaded, to tell one load from a loop of them
let loads = 0;
export const loadCalls = () => loads;
export const resetLoadCalls = () => { loads = 0; };
export function replaceTheme() {
    theme = new Theme();
    emitSignal(THEME_CONTEXT, 'changed');
}
export const St = {
    ThemeContext: {
        get_for_stage: () => ({
            get_theme: () => theme,
            connect(signal, callback) {
                const id = ++handlerNext;
                handlers.set(id, [THEME_CONTEXT, signal, callback]);
                return id;
            },
            disconnect(id) { if (!handlers.delete(id)) throw new Error('unknown handler'); },
        }),
    },
};
globalThis.global = {stage: {}};
