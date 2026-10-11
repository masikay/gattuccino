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

export const state = {scale: 1};
export const St = {ThemeContext: {get_for_stage: () => ({get scale_factor() { return state.scale; }})}};

class Panel extends Emitter {
    constructor() { super(); this.height = 32; this.classes = new Set(); }
    add_style_class_name(name) { this.classes.add(name); }
    remove_style_class_name(name) { this.classes.delete(name); }
}
export const Main = {
    panel: new Panel(),
    layoutManager: Object.assign(new Emitter(), {primaryMonitor: {index: 0, x: 0, y: 0, width: 1920, height: 1080}}),
};
export class Extension {}

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
