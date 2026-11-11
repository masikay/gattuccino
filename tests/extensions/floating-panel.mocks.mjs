import assert from 'node:assert/strict';

// Stand-ins for the parts of GNOME Shell the floating-panel extension uses
export class Emitter {
    constructor() { this._handlers = new Map(); this._next = 0; }
    connect(signal, callback) { const id = ++this._next; this._handlers.set(id, [signal, callback]); return id; }
    disconnect(id) { if (!this._handlers.delete(id)) throw new Error(`disconnect of unknown id ${id}`); }
    emit(signal, ...args) { for (const [s, callback] of [...this._handlers.values()]) if (s === signal) callback(this, ...args); }
    get handlerCount() { return this._handlers.size; }
}

const idle = new Map();
let idleNext = 0;
export const GLib = {
    PRIORITY_DEFAULT: 0, SOURCE_REMOVE: false,
    idle_add(_priority, callback) { const id = ++idleNext; idle.set(id, callback); return id; },
    source_remove(id) { if (!idle.delete(id)) throw new Error('unknown source'); },
};
export const pendingIdle = () => idle.size;
export function settle() { while (idle.size) for (const [id, callback] of [...idle]) { idle.delete(id); callback(); } }

class WindowActor extends Emitter {}
export const Meta = {WindowActor, WindowType: {NORMAL: 0, DESKTOP: 1, DOCK: 2, DIALOG: 3, MODAL_DIALOG: 4}};

export const state = {scale: 1, gap: 6, transition: 250};
export const St = {ThemeContext: {get_for_stage: () => ({get scale_factor() { return state.scale; }})}};
export const Clutter = {AnimationMode: {EASE_OUT_QUAD: 'ease-out-quad'}};

// Enough of St.Widget and Clutter.Actor for the slide between the two states:
// the margins the theme would give the panel, and an ease() that records the
// animation instead of running it.
class Panel extends Emitter {
    constructor() {
        super();
        this.height = 32;
        this.classes = new Set();
        this.mapped = true;
        this.margin_top = this.margin_left = this.margin_right = 0;
        this.translation_y = 0;
        this.eased = null;
        this.transitions = new Set();
        this._styleDirty = false;
    }

    // The gap of the theme's '#panel.floating-panel' rule, and none of it while
    // docked. St applies the margins of the matching rules as soon as the
    // classes change, as long as the panel is on screen, and on ensure_style()
    // otherwise.
    _applyMargins() {
        let gap = this.classes.has('floating-panel') ? state.gap : 0;
        // What is set on the panel itself wins over the theme
        const inline = /margin:\s*(\d+)px/.exec(this._style ?? '');
        if (inline && this.classes.has('floating-panel')) gap = Number(inline[1]);
        this.margin_top = this.margin_left = this.margin_right = gap;
        this._styleDirty = false;
    }
    get style() { return this._style ?? ''; }
    set style(value) { this._style = value; this._restyle(); }
    _restyle() { if (this.mapped) this._applyMargins(); else this._styleDirty = true; }
    add_style_class_name(name) { this.classes.add(name); this._restyle(); }
    remove_style_class_name(name) { if (this.classes.delete(name)) this._restyle(); }
    ensure_style() { if (this._styleDirty) this._applyMargins(); }
    get_theme_node() { return {get_transition_duration: () => state.transition}; }

    ease({duration, mode, ...targets}) {
        const from = {};
        for (const property of Object.keys(targets)) {
            from[property] = this[property];
            this.transitions.add(property.replaceAll('_', '-'));
        }
        this.eased = {duration, mode, targets, from};
    }
    remove_transition(property) {
        this.transitions.delete(property);
        if (!this.transitions.size) this.eased = null;
    }
    // What Clutter leaves behind once the transitions have run their course
    finishEase() {
        assert.ok(this.eased, 'no animation to finish');
        Object.assign(this, this.eased.targets);
        this.transitions.clear();
        this.eased = null;
    }
}

export const Main = {
    panel: new Panel(),
    layoutManager: Object.assign(new Emitter(), {primaryMonitor: {index: 0, x: 0, y: 0, width: 1920, height: 1080}}),
};
// The settings of the extension, changed while it runs
export const prefs = Object.assign(new Emitter(), {
    values: {},
    get_int(key) { return this.values[key]; },
    get_string(key) { return this.values[key]; },
});
export const resetPrefs = () => { prefs.values = {gap: 6, radius: 'round'}; };
resetPrefs();
export function setPref(key, value) {
    prefs.values[key] = value;
    prefs.emit('changed', key);
}
export class Extension { getSettings() { return prefs; } }

export class Window {
    constructor(properties) { Object.assign(this, {y: 300, monitor: 0, minimized: false, type: 0, app: null, showing: true}, properties); }
    get_monitor() { return this.monitor; }
    showing_on_its_workspace() { return this.showing; }
    get_window_type() { return this.type; }
    get_gtk_application_id() { return this.app; }
    get_frame_rect() { return {x: 0, y: this.y, width: 800, height: 600}; }
}

export const workspace = {windows: [], list_windows() { return this.windows; }};
globalThis.global = {
    stage: {}, window_group: new Emitter(),
    workspace_manager: Object.assign(new Emitter(), {get_active_workspace: () => workspace}),
    actors: [], get_window_actors() { return this.actors; },
};
