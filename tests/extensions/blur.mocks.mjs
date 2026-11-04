import assert from 'node:assert/strict';

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
    // What a theme node answers: the blur properties, the background alpha, the
    // corner radii of the surface and the width of its border.
    theme: {radius: 32, brightness: 1, alpha: 204, corners: [16, 16, 16, 16], border: 0},
};

class ThemeNode {
    constructor(actor) { this._theme = actor.theme ?? state.theme; }
    lookup_length(name) {
        const {radius} = this._theme;
        return name === '-gattuccino-blur-radius' && radius != null ? [true, radius] : [false, 0];
    }
    lookup_double(name) {
        const {brightness} = this._theme;
        return name === '-gattuccino-blur-brightness' && brightness != null ? [true, brightness] : [false, 0];
    }
    get_background_color() { return {alpha: this._theme.alpha}; }
    get_border_radius(corner) { return this._theme.corners[corner]; }
    get_border_width() { return this._theme.border; }
}

class Binding {
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
            allocated: true, destroyed: false,
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

    /**
     * As in the Shell: the actor says it is going, and is then taken out of its
     * parent. Anything touched after this throws, the way GJS refuses to let a
     * disposed object be used.
     */
    destroy() {
        if (this.destroyed) return;
        for (const child of this.get_children()) child.destroy();
        this.emit('destroy');
        this.destroyed = true;
        const parent = this._parent;
        this._parent = null;
        if (parent) {
            parent._children = parent._children.filter(c => c !== this);
            parent.emit('child-removed', this);
        }
        this._disposed = true;
    }
    _check() { if (this._disposed) throw new Error(`${this.name || this.style_class || 'actor'} has been already disposed`); }

    set_position(x, y) { this._check(); this.x = x; this.y = y; this._notifyMoved(); }
    set_size(width, height) { this._check(); this.width = width; this.height = height; this._notifyMoved(); }
    set_pivot_point(x, y) { this.pivot_point = {x, y}; }
    get_size() { return [this.width, this.height]; }
    has_allocation() { return this.allocated; }
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
    /** Which of the stage's views the actor is on: none means never painted. */
    peek_stage_views() { return this.views ?? [1]; }

    has_style_class_name(name) { return this.style_class.split(' ').includes(name); }
    get_theme_node() {
        this._check();
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

    /** Connecting and disconnecting go through the disposal check too. */
    connect(signal, callback) { this._check(); return super.connect(signal, callback); }
    disconnect(id) { this._check(); super.disconnect(id); }
}

export class Clone extends Actor {
    constructor(properties) { super(properties); this.source = properties.source; }
}

export class BoxPointer extends Actor {}

class ShaderEffect {
    constructor() { this.uniforms = {}; this.repaints = 0; }
    /** Clutter paints the effect through a copy a few pixels larger than the actor. */
    get_target_size() { const actor = this.get_actor(); return [true, actor.width + 3, actor.height + 3]; }
    vfunc_paint_target() {}
    set_uniform_value(name, value) { this.uniforms[name] = value; }
    set_uniform_float(name, components, values) { this.uniforms[name] = {components, values}; }
    queue_repaint() { this.repaints++; }
    get_actor() { return this.actor; }
}

class BlurEffect {
    constructor(properties = {}) { Object.assign(this, {radius: 0, brightness: 1, mode: 0, repaints: 0}, properties); }
    set(properties) { Object.assign(this, properties); }
    queue_repaint() { this.repaints++; }
}

// Work queued for the end of the frame
const laters = new Map();
let laterNext = 0;
export const pendingLaters = () => laters.size;
export function settle(limit = 100) {
    for (let round = 0; laters.size; round++) {
        if (round >= limit) throw new Error('the work queued for the end of the frame never settles');
        for (const [id, callback] of [...laters]) {
            laters.delete(id);
            // Work that asks to run again on the next frame does, as in Clutter
            if (callback() === GLib.SOURCE_CONTINUE) laters.set(id, callback);
        }
    }
}

export const GLib = {PRIORITY_DEFAULT: 0, SOURCE_REMOVE: false, SOURCE_CONTINUE: true};
export const Clutter = {Clone, ShaderEffect};
export const Cogl = {SnippetHook: {FRAGMENT: 2048}, Snippet: {new: (hook, declarations, post) => ({hook, declarations, post})}};
export const Shell = {BlurEffect, BlurMode: {ACTOR: 0, BACKGROUND: 1}};
export const Meta = {BackgroundGroup: class BackgroundGroup extends Actor {}, LaterType: {RESIZE: 0, BEFORE_REDRAW: 4}};
export const themeContext = new Emitter();
export const St = {
    ThemeContext: {get_for_stage: () => themeContext},
    Widget: Actor,
    Corner: {TOPLEFT: 0, TOPRIGHT: 1, BOTTOMRIGHT: 2, BOTTOMLEFT: 3},
    Side: {TOP: 0, RIGHT: 1, BOTTOM: 2, LEFT: 3},
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

export const backgrounds = [];
export const Background = {
    BackgroundManager: class BackgroundManager {
        constructor({container, monitorIndex}) {
            Object.assign(this, {container, monitorIndex, alive: true});
            backgrounds.push(this);
        }
        destroy() { this.alive = false; }
    },
};

export const Main = {
    panel: null,
    layoutManager: null,
    overview: null,
};
export class Extension {}

/** A desktop to blur: the UI group with a top bar and an overview in it. */
export function desktop() {
    backgrounds.length = 0;
    const uiGroup = new Actor({name: 'uiGroup', width: 1600, height: 900});
    const windowGroup = new Actor({name: 'windowGroup', width: 1600, height: 900});
    const panelBox = new Actor({name: 'panelBox', width: 1600, height: 38});
    const panel = new Actor({name: 'panel', x: 6, y: 6, width: 1588, height: 32});
    const overviewGroup = new Actor({name: 'overviewGroup', width: 1600, height: 900, visible: false, mapped: false});
    panelBox.add_child(panel);
    uiGroup.add_child(windowGroup);
    uiGroup.add_child(overviewGroup);
    uiGroup.add_child(panelBox);

    Main.panel = panel;
    Main.overview = new Emitter();
    Main.layoutManager = Object.assign(new Emitter(), {
        uiGroup, panelBox, overviewGroup,
        monitors: [{index: 0, x: 0, y: 0, width: 1600, height: 900}],
    });
    globalThis.global = {
        window_group: windowGroup,
        compositor: {
            get_laters: () => ({
                add(_type, callback) { const id = ++laterNext; laters.set(id, callback); return id; },
                remove(id) { laters.delete(id); },
            }),
        },
    };
    return {uiGroup, windowGroup, panelBox, panel, overviewGroup};
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
export {assert};
