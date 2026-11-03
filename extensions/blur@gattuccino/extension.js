import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {BoxPointer} from 'resource:///org/gnome/shell/ui/boxpointer.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// A stylesheet cannot blur what is behind it, so the Gattuccino theme states
// what it would like blurred and this extension does it. Both properties sit on
// the surface itself (the blur preference puts them on the top bar, on popup
// menus and on the dock); with another theme nothing carries them, and this
// extension then changes nothing.
const RADIUS_PROPERTY = '-gattuccino-blur-radius';
const BRIGHTNESS_PROPERTY = '-gattuccino-blur-brightness';

// The surfaces to look for. Each has a shape, the actor the theme fills and
// rounds, and an anchor, the actor that is placed and animated as a whole.
const POPUP_SHAPE = 'popup-menu-content';
const DOCK_SHAPE = 'dash-background';
const DOCK_CONTAINER = 'dashtodockContainer';
const BACKDROP_NAME = 'gattuccino-blur';

// A menu's content sits inside a bin inside its box pointer
const POPUP_DEPTH = 3;

// Every way a surface is moved or resized
const MOVED = ['notify::allocation', 'notify::x', 'notify::y',
    'notify::translation-x', 'notify::translation-y'];
const DOCK_DEPTH = 5;

const CORNERS = [St.Corner.TOPLEFT, St.Corner.TOPRIGHT, St.Corner.BOTTOMRIGHT, St.Corner.BOTTOMLEFT];

// Cuts what has been painted to a rounded rectangle, the one the theme draws
// for the surface. Without it the blur would show as a square behind the
// rounded corners of the bar, of a menu or of the dock. The corners are given
// in the order of CORNERS, and `distance` is the usual signed distance to a
// rounded box: negative inside, positive outside, crossing zero at the edge.
const MASK_DECLARATIONS = `
uniform float width;
uniform float height;
uniform vec4 corners;
`;
const MASK_SOURCE = `
vec2 size = vec2(width, height);
vec2 half_size = size * 0.5;
vec2 from_center = cogl_tex_coord0_in.st * size - half_size;
float radius = from_center.x < 0.0
    ? (from_center.y < 0.0 ? corners.x : corners.w)
    : (from_center.y < 0.0 ? corners.y : corners.z);
vec2 corner = abs(from_center) - half_size + vec2(radius);
float distance = min(max(corner.x, corner.y), 0.0) + length(max(corner, vec2(0.0))) - radius;
cogl_color_out *= 1.0 - smoothstep(-0.5, 0.5, distance);
`;

function floatValue(number) {
    const value = new GObject.Value();
    value.init(GObject.TYPE_FLOAT);
    value.set_float(number);
    return value;
}

const RoundedMaskEffect = GObject.registerClass({
    GTypeName: 'GattuccinoRoundedMaskEffect',
}, class RoundedMaskEffect extends Clutter.ShaderEffect {
    _init() {
        super._init();
        this._corners = [0, 0, 0, 0];
    }

    setCorners(corners) {
        this._corners = corners;
        this.queue_repaint();
    }

    vfunc_get_static_snippet() {
        return Cogl.Snippet.new(Cogl.SnippetHook.FRAGMENT, MASK_DECLARATIONS, MASK_SOURCE);
    }

    vfunc_paint_target(node, paintContext) {
        const [width, height] = this.get_actor().get_size();
        const limit = Math.min(width, height) / 2;
        this.set_uniform_value('width', floatValue(width));
        this.set_uniform_value('height', floatValue(height));
        this.set_uniform_float('corners', 4, this._corners.map(radius => Math.min(radius, limit)));
        super.vfunc_paint_target(node, paintContext);
    }
});

/**
 * The blur behind one surface: a copy of everything the Shell is drawn over
 * (the wallpaper and the windows), cut to the shape of the surface, blurred,
 * and put right behind it.
 *
 * It is a sibling of the anchor rather than a child of the surface, because a
 * child would be painted over the surface's own color instead of under it. So
 * it follows the anchor by hand: where it is, and the small zoom and fade a
 * menu opens with.
 */
class Backdrop {
    constructor(shape, anchor) {
        this._shape = shape;
        this._anchor = anchor;
        this._wanted = false;
        this._restackId = 0;

        this._clone = new Clutter.Clone({source: global.window_group});
        this._actor = new St.Widget({name: BACKDROP_NAME, clip_to_allocation: true});
        this._actor.add_child(this._clone);

        // The mask is added first so that it is applied to the blurred copy,
        // and not the other way round: an effect wraps those added after it.
        this._mask = new RoundedMaskEffect();
        this._blur = new Shell.BlurEffect({mode: Shell.BlurMode.ACTOR});
        this._actor.add_effect_with_name('mask', this._mask);
        this._actor.add_effect_with_name('blur', this._blur);

        anchor.get_parent().insert_child_below(this._actor, anchor);

        this._bindings = ['opacity', 'scale-x', 'scale-y', 'translation-x', 'translation-y']
            .map(property => anchor.bind_property(property, this._actor, property,
                GObject.BindingFlags.SYNC_CREATE));

        // A surface is moved in more ways than one: a menu is given a fixed
        // position, the bar is allocated, and the floating bar slides under its
        // own margin by a translation. Each of them is followed, as not all of
        // them change the allocation.
        this._signals = [
            ...MOVED.map(signal => [shape, signal, () => this._place()]),
            ...MOVED.map(signal => [anchor, signal, () => this._place()]),
            [shape, 'notify::mapped', () => this.refresh()],
            [shape, 'style-changed', () => this.refresh()],
            [anchor, 'notify::visible', () => this._show()],
        ].map(([object, signal, callback]) => [object, object.connect(signal, callback)]);

        this.refresh();
    }

    destroy() {
        if (this._restackId) {
            GLib.source_remove(this._restackId);
            this._restackId = 0;
        }
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = [];
        for (const binding of this._bindings)
            binding.unbind();
        this._bindings = [];
        this._actor.destroy();
        this._actor = null;
    }

    /** Take what the theme asks for, and whether it asks at all. */
    refresh() {
        // A menu that has never been opened has no style of its own yet, and
        // asking for the theme node of an actor that is not on screen is an
        // error. It is asked again when the menu is mapped.
        if (!this._shape.mapped) {
            this._wanted = false;
            this._show();
            return;
        }

        const node = this._shape.get_theme_node();
        const [hasRadius, radius] = node.lookup_length(RADIUS_PROPERTY, false);
        const [hasBrightness, brightness] = node.lookup_double(BRIGHTNESS_PROPERTY, false);

        // A surface that is not translucent has nothing to show through it: in
        // the overview the bar has no background at all, and docked it can be
        // solid. Blurring a copy of the screen for it would be work for
        // nothing, so the blur steps aside until it is translucent again.
        const alpha = node.get_background_color().alpha;

        this._wanted = hasRadius && radius > 0 && alpha > 0 && alpha < 255;
        this._show();
        if (!this._wanted)
            return;

        this._blur.set({radius: Math.round(radius), brightness: hasBrightness ? brightness : 1});
        this._mask.setCorners(CORNERS.map(corner => node.get_border_radius(corner)));
        this._place();
    }

    _show() {
        this._actor.visible = this._wanted && this._anchor.visible;
        if (this._actor.visible)
            this._queueRestack();
    }

    // A menu is raised to the top of its parent as it opens, which would leave
    // its blur behind, under whatever the menu is now above. The raise is done
    // once the menu has been shown, so this follows on the next turn of the
    // loop, before anything is painted.
    _queueRestack() {
        if (this._restackId)
            return;

        this._restackId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._restackId = 0;
            const parent = this._anchor.get_parent();
            if (parent && this._actor.get_parent() === parent)
                parent.set_child_below_sibling(this._actor, this._anchor);
            return GLib.SOURCE_REMOVE;
        });
    }

    _place() {
        // Where the shape sits inside the anchor, which may be a few actors up
        // (a menu's content is in a bin inside its box pointer) and may be
        // sliding (the floating bar docks by moving under its own margin). The
        // anchor's own scale and translation are left out: they are bound to
        // the backdrop instead, so that it is animated with the anchor.
        //
        // Every reading is of the allocation, never of x/y/width/height: those
        // answer with the size an actor would like to be, not the one it has,
        // while a relayout is pending, and the allocation that follows is often
        // the same one as before and so goes unannounced.
        const box = this._shape.get_allocation_box();
        let x = this._anchor.get_allocation_box().x1;
        let y = this._anchor.get_allocation_box().y1;
        for (let actor = this._shape; actor && actor !== this._anchor; actor = actor.get_parent()) {
            const allocation = actor.get_allocation_box();
            x += allocation.x1 + actor.translation_x;
            y += allocation.y1 + actor.translation_y;
        }

        const [width, height] = [box.get_width(), box.get_height()];
        this._actor.set_position(x, y);
        this._actor.set_size(width, height);

        // Line the copy up with the screen it is a copy of
        const [stageX, stageY] = this._shape.get_transformed_position();
        this._clone.set_position(-stageX, -stageY);

        // Zoom about the same point as the anchor, so that the blur follows the
        // way a menu opens instead of appearing at full size
        const anchorBox = this._anchor.get_allocation_box();
        const pivot = this._anchor.pivot_point;
        this._actor.set_pivot_point(
            width > 0 ? (anchorBox.x1 + pivot.x * anchorBox.get_width() - x) / width : 0,
            height > 0 ? (anchorBox.y1 + pivot.y * anchorBox.get_height() - y) / height : 0);

        // A copy of the screen does not change by itself, so nothing else would
        // ask for it to be painted again at its new size and shape.
        this._actor.queue_redraw();
    }
}

export default class BlurExtension extends Extension {
    enable() {
        this._backdrops = new Map();   // anchor actor -> Backdrop
        this._signals = [];

        const uiGroup = Main.layoutManager.uiGroup;
        this._connect(uiGroup, 'child-added', (_group, actor) => this._watch(actor));
        this._connect(uiGroup, 'child-removed', (_group, actor) => this._unwatch(actor));

        for (const actor of uiGroup.get_children())
            this._watch(actor);
    }

    disable() {
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = null;

        for (const backdrop of this._backdrops.values())
            backdrop.destroy();
        this._backdrops = null;
    }

    _connect(object, signal, callback) {
        this._signals.push([object, object.connect(signal, callback)]);
    }

    // Everything the theme may have asked to blur is in the UI group: the top
    // bar, menus as they are created, and the dock of Dash to Dock.
    _watch(actor) {
        if (actor.name === BACKDROP_NAME)
            return;
        if (actor === Main.layoutManager.panelBox) {
            this._add(Main.panel, actor);
            return;
        }
        // The overview is one surface of its own: it fills the screen, and the
        // theme turns the solid color GNOME gives it into glass. The desktop
        // behind it is hidden while it is open, which a copy still draws.
        if (actor === Main.layoutManager.overviewGroup) {
            this._add(actor, actor);
            return;
        }
        if (actor.name === DOCK_CONTAINER) {
            const dock = findByStyleClass(actor, DOCK_SHAPE, DOCK_DEPTH);
            if (dock)
                this._add(dock, actor);
            return;
        }
        const content = findByStyleClass(actor, POPUP_SHAPE, POPUP_DEPTH);
        if (content)
            this._add(content, boxPointerOf(content) ?? actor);
    }

    _unwatch(actor) {
        for (const [anchor, backdrop] of this._backdrops) {
            if (anchor === actor || anchor.get_parent() === actor || !anchor.get_parent()) {
                this._backdrops.delete(anchor);
                backdrop.destroy();
            }
        }
    }

    _add(shape, anchor) {
        if (anchor && !this._backdrops.has(anchor) && anchor.get_parent())
            this._backdrops.set(anchor, new Backdrop(shape, anchor));
    }
}

/** The actor itself, or the first one under it with this style class. */
function findByStyleClass(actor, styleClass, depth) {
    if (actor.has_style_class_name?.(styleClass))
        return actor;
    if (depth <= 0)
        return null;
    for (const child of actor.get_children()) {
        const found = findByStyleClass(child, styleClass, depth - 1);
        if (found)
            return found;
    }
    return null;
}

/** The box pointer a menu's content is in: the actor its whole menu is moved
 * and animated by. Menus are in the UI group either on their own or inside a
 * container of their own, so it is not simply the top of the chain. */
function boxPointerOf(content) {
    for (let actor = content; actor; actor = actor.get_parent()) {
        if (actor instanceof BoxPointer)
            return actor;
    }
    return null;
}
