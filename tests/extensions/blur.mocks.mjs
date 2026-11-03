// Stand-ins for the parts of GNOME Shell the blur extension uses: enough of an
// actor tree, of theme nodes and of effects to place a backdrop and to say what
// should be blurred.

class Emitter {
    constructor() { this._handlers = new Map(); this._next = 0; }
    connect(signal, callback) { const id = ++this._next; this._handlers.set(id, [signal, callback]); return id; }
    disconnect(id) { if (!this._handlers.delete(id)) throw new Error(`disconnect of unknown id ${id}`); }
    emit(signal, ...args) { for (const [s, callback] of [...this._handlers.values()]) if (s === signal) callback(this, ...args); }
    get handlerCount() { return this._handlers.size; }
}

export const state = {
    // What a theme node answers: the blur properties, the background alpha and
    // the corner radii of the surface.
    theme: {radius: 32, brightness: 1.12, alpha: 204, corners: [16, 16, 16, 16]},
};

export class ThemeNode {
    constructor(actor) { this._actor = actor; }
    lookup_length(name) {
        const {radius} = this._actor.theme ?? state.theme;
        return name === '-gattuccino-blur-radius' && radius != null ? [true, radius] : [false, 0];
    }
    lookup_double(name) {
        const {brightness} = this._actor.theme ?? state.theme;
        return name === '-gattuccino-blur-brightness' && brightness != null ? [true, brightness] : [false, 0];
    }
    get_background_color() { return {alpha: (this._actor.theme ?? state.theme).alpha}; }
    get_border_radius(corner) { return (this._actor.theme ?? state.theme).corners[corner]; }
}

export class Binding {
    constructor(source, sourceProperty, target, targetProperty) {
        Object.assign(this, {source, sourceProperty, target, targetProperty, bound: true});
        this.sync();
    }
    sync() { if (this.bound) this.target[property(this.targetProperty)] = this.source[property(this.sourceProperty)]; }
    unbind() { this.bound = false; }
}
const property = name => name.replaceAll('-', '_');

export class Actor extends Emitter {
    constructor(properties = {}) {
        super();
        Object.assign(this, {
            x: 0, y: 0, width: 0, height: 0, translation_x: 0, translation_y: 0,
            opacity: 255, visible: true, mapped: true, scale_x: 1, scale_y: 1,
            pivot_point: {x: 0, y: 0}, style_class: '', name: '',
            destroyed: false,
        }, properties);
        this._children = [];
        this._parent = null;
        this._effects = new Map();
        this._bindings = [];
        this._redraws = 0;
    }

    add_child(child) { child._parent = this; this._children.push(child); this.emit('child-added', child); }
    insert_child_below(child, sibling) {
        child._parent = this;
        const at = sibling ? this._children.indexOf(sibling) : this._children.length;
        this._children.splice(at < 0 ? this._children.length : at, 0, child);
        this.emit('child-added', child);
    }
    set_child_below_sibling(child, sibling) {
        this._children = this._children.filter(c => c !== child);
        const at = sibling ? this._children.indexOf(sibling) : this._children.length;
        this._children.splice(at < 0 ? this._children.length : at, 0, child);
    }
    set_child_above_sibling(child, sibling) {
        this._children = this._children.filter(c => c !== child);
        const at = sibling ? this._children.indexOf(sibling) + 1 : this._children.length;
        this._children.splice(at, 0, child);
    }
    remove_child(child) {
        this._children = this._children.filter(c => c !== child);
        child._parent = null;
        this.emit('child-removed', child);
    }
    get_parent() { return this._parent; }
    get_children() { return [...this._children]; }
    destroy() { this.destroyed = true; this._parent?.remove_child(this); }

    set_position(x, y) { this.x = x; this.y = y; this._notifyMoved(); }
    set_size(width, height) { this.width = width; this.height = height; this._notifyMoved(); }
    set_pivot_point(x, y) { this.pivot_point = {x, y}; }
    get_size() { return [this.width, this.height]; }
    /** What the actor was last given, which is what the extension reads. */
    get_allocation_box() {
        const [x, y, width, height] = [this.x, this.y, this.width, this.height];
        return {x1: x, y1: y, x2: x + width, y2: y + height, get_width: () => width, get_height: () => height};
    }
    get_transformed_position() {
        let [x, y] = [0, 0];
        for (let actor = this; actor; actor = actor.get_parent())
            [x, y] = [x + actor.x + actor.translation_x, y + actor.y + actor.translation_y];
        return [x, y];
    }
    queue_redraw() { this._redraws++; }

    has_style_class_name(name) { return this.style_class.split(' ').includes(name); }
    get_theme_node() {
        if (!this.mapped) throw new Error('get_theme_node() while unmapped');
        return new ThemeNode(this);
    }

    add_effect_with_name(name, effect) { this._effects.set(name, effect); effect.actor = this; }
    get_effect(name) { return this._effects.get(name) ?? null; }

    bind_property(sourceProperty, target, targetProperty) {
        const binding = new Binding(this, sourceProperty, target, targetProperty);
        this._bindings.push(binding);
        return binding;
    }
    /** What Clutter does for a bound property: here it is done by hand. */
    set(properties) {
        Object.assign(this, properties);
        for (const binding of this._bindings) binding.sync();
        for (const name of Object.keys(properties)) this.emit(`notify::${name.replaceAll('_', '-')}`);
        this._notifyMoved();
    }

    _notifyMoved() {
        this.emit('notify::allocation');
        this.emit('notify::x');
    }
}

export class Clone extends Actor {
    constructor(properties) { super(properties); this.source = properties.source; }
}

export class BoxPointer extends Actor {}

class ShaderEffect {
    constructor() { this.uniforms = {}; this.repaints = 0; }
    vfunc_paint_target() {}
    set_uniform_value(name, value) { this.uniforms[name] = value; }
    set_uniform_float(name, components, values) { this.uniforms[name] = {components, values}; }
    queue_repaint() { this.repaints++; }
    get_actor() { return this.actor; }
}

class BlurEffect {
    constructor(properties = {}) { Object.assign(this, {radius: 0, brightness: 1, mode: 0}, properties); }
    set(properties) { Object.assign(this, properties); }
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

export const Clutter = {Clone, ShaderEffect};
export const Cogl = {SnippetHook: {FRAGMENT: 2048}, Snippet: {new: (hook, declarations, post) => ({hook, declarations, post})}};
export const Shell = {BlurEffect, BlurMode: {ACTOR: 0, BACKGROUND: 1}};
export const St = {
    Widget: Actor,
    Corner: {TOPLEFT: 0, TOPRIGHT: 1, BOTTOMRIGHT: 2, BOTTOMLEFT: 3},
};
export const GObject = {
    registerClass: (meta, klass) => klass ?? meta,
    ParamFlags: {READWRITE: 3},
    TYPE_FLOAT: 'float',
    BindingFlags: {SYNC_CREATE: 1},
    Value: class {
        init(type) { this.type = type; }
        set_float(value) { this.value = value; }
    },
};

export const Main = {
    panel: null,
    layoutManager: {uiGroup: null, panelBox: null, overviewGroup: null},
};
export class Extension {}

/** A desktop to blur: the UI group with a top bar in it. */
export function desktop() {
    const uiGroup = new Actor({name: 'uiGroup', width: 1600, height: 900});
    const panelBox = new Actor({name: 'panelBox', width: 1600, height: 38});
    const panel = new Actor({name: 'panel', x: 6, y: 6, width: 1588, height: 32});
    const overviewGroup = new Actor({name: 'overviewGroup', width: 1600, height: 900, visible: false, mapped: false});
    panelBox.add_child(panel);
    uiGroup.add_child(overviewGroup);
    uiGroup.add_child(panelBox);
    Main.panel = panel;
    Main.layoutManager.uiGroup = uiGroup;
    Main.layoutManager.panelBox = panelBox;
    Main.layoutManager.overviewGroup = overviewGroup;
    globalThis.global = {window_group: new Actor({name: 'windowGroup'})};
    return {uiGroup, panelBox, panel, overviewGroup};
}

/** A menu: content in a bin in a box pointer, the way the Shell builds one. */
export function menu({x = 100, y = 40, width = 400, height = 300, wrapped = false} = {}) {
    const pointer = new BoxPointer({x, y, width, height: height + 6, style_class: 'popup-menu-boxpointer popup-menu'});
    const bin = new Actor({y: 6, width, height});
    const content = new Actor({width, height, style_class: 'popup-menu-content'});
    bin.add_child(content);
    pointer.add_child(bin);
    if (!wrapped)
        return {top: pointer, pointer, content};

    const wrapper = new Actor({style_class: 'panel-menu'});
    wrapper.add_child(pointer);
    return {top: wrapper, pointer, content};
}

export const backdropsIn = actor => actor.get_children().filter(child => child.name === 'gattuccino-blur');
