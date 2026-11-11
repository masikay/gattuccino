// Stand-ins for the widgets and the settings the preferences windows of the
// extensions are made of, enough to drive them the way a person would: by
// changing what a row shows, and seeing what the setting then says.

export const GET = 2, DEFAULT = 0;

/** A widget: properties that say so when they change, signals, and children. */
class Widget {
    constructor(properties = {}) {
        Object.assign(this, properties);
        this._handlers = [];
        this.children = [];
        this.cssClasses = new Set();
        return new Proxy(this, {
            set(target, key, value) {
                const old = target[key];
                target[key] = value;
                if (typeof key === 'string' && !key.startsWith('_') && key !== 'children' && old !== value)
                    target.emit(`notify::${key}`);
                return true;
            },
        });
    }
    connect(signal, callback) { this._handlers.push([signal, callback]); return this._handlers.length; }
    emit(signal, ...args) { for (const [s, callback] of [...this._handlers]) if (s === signal) callback(this, ...args); }
    add(child) { this.children.push(child); }
    add_suffix(child) { this.children.push(child); }
    add_css_class(name) { this.cssClasses.add(name); }
}

export const Adw = {
    PreferencesPage: class extends Widget {},
    PreferencesGroup: class extends Widget {},
    SpinRow: class extends Widget {},
    SwitchRow: class extends Widget {},
    ComboRow: class extends Widget {},
    EntryRow: class extends Widget {},
    ActionRow: class extends Widget {},
};
export const Gtk = {
    Adjustment: class extends Widget {},
    Button: class extends Widget {},
    StringList: {new: items => ({items})},
    FileDialog: class extends Widget {},
    FileFilter: class extends Widget { add_mime_type() {} },
    Align: {CENTER: 3},
};
export const Gio = {
    SettingsBindFlags: {DEFAULT, GET},
    ListStore: class extends Widget { append() {} },
    AppInfo: {create_from_commandline: () => ({launch() {}})},
    AppInfoCreateFlags: {NONE: 0},
};

/** A GSettings: values, 'changed' signals, and bind() */
export class Settings {
    constructor(values) { this.values = {...values}; this._handlers = []; }
    connect(signal, callback) { this._handlers.push([signal, callback]); return this._handlers.length; }
    _emit(key) { for (const [s, cb] of this._handlers) if (s === 'changed' || s === `changed::${key}`) cb(this, key); }
    get_int(key) { return this.values[key]; }
    get_boolean(key) { return this.values[key]; }
    get_string(key) { return this.values[key]; }
    set_string(key, value) { this._set(key, value); }
    set_int(key, value) { this._set(key, value); }
    set_boolean(key, value) { this._set(key, value); }
    _set(key, value) {
        if (this.values[key] === value) return;
        this.values[key] = value;
        this._emit(key);
    }
    bind(key, widget, property, flags) {
        widget[property] = this.values[key];
        this.connect(`changed::${key}`, () => { widget[property] = this.values[key]; });
        if (flags !== GET)
            widget.connect(`notify::${property}`, () => this._set(key, widget[property]));
    }
}

export class ExtensionPreferences {
    getSettings() { return ExtensionPreferences.settings; }
}

/** A window to put the pages in, and a way to find the rows by what they say */
export class Window extends Widget {}
export function rows(window) {
    const found = [];
    const walk = widget => { found.push(widget); widget.children.forEach(walk); };
    walk(window);
    return found;
}
export const row = (window, title) => rows(window).find(widget => widget.title === title);
