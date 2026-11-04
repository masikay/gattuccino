import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {BoxPointer} from 'resource:///org/gnome/shell/ui/boxpointer.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// A stylesheet cannot blur what is behind it, so the Gattuccino theme states
// what it would like blurred and this extension does it. Both properties sit on
// the surface itself (the blur preference puts them on the top bar, on popup
// menus, on the overview and on the dock); with another theme nothing carries
// them, and this extension then changes nothing.
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

const DOCK_DEPTH = 5;

// Every way a surface is moved or resized
const MOVED = ['notify::allocation', 'notify::x', 'notify::y',
    'notify::translation-x', 'notify::translation-y'];

const CORNERS = [St.Corner.TOPLEFT, St.Corner.TOPRIGHT, St.Corner.BOTTOMRIGHT, St.Corner.BOTTOMLEFT];

// Cuts what has been painted to a rounded rectangle, the one the theme fills
// for the surface. Without it the blur would show as a square behind the
// rounded corners of the bar, of a menu or of the dock. `inset` is the width of
// the surface's border, which is drawn around the fill and not over it, so the
// blur stops where the fill does and the two corners sit on top of each other.
const MASK_DECLARATIONS = `
uniform vec2 offscreen;
uniform vec2 size;
uniform float inset;
uniform vec4 corners;
`;
const MASK_SOURCE = `
vec2 from_center = cogl_tex_coord0_in.st * offscreen - offscreen * 0.5;
float radius = from_center.x < 0.0
    ? (from_center.y < 0.0 ? corners.x : corners.w)
    : (from_center.y < 0.0 ? corners.y : corners.z);
radius = max(radius - inset, 0.0);
vec2 half_size = size * 0.5 - vec2(inset);
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
        this._inset = 0;
    }

    setShape(corners, inset) {
        this._corners = corners;
        this._inset = inset;
        this.queue_repaint();
    }

    vfunc_get_static_snippet() {
        return Cogl.Snippet.new(Cogl.SnippetHook.FRAGMENT, MASK_DECLARATIONS, MASK_SOURCE);
    }

    vfunc_paint_target(node, paintContext) {
        const box = this.get_actor().get_allocation_box();
        const [width, height] = [box.get_width(), box.get_height()];
        // What is painted here is an offscreen copy, and Clutter makes it a
        // few pixels larger than the actor. Its texture coordinates therefore
        // span more than the actor does, which on a bar 32 pixels tall is a
        // tenth of its height: the shape has to be measured in the copy's own
        // pixels, with the actor's box centered in it, or its corners come out
        // somewhere else entirely.
        const [known, textureWidth, textureHeight] = this.get_target_size();
        const limit = Math.min(width, height) / 2;
        this.set_uniform_float('offscreen', 2,
            known ? [textureWidth, textureHeight] : [width, height]);
        this.set_uniform_float('size', 2, [width, height]);
        this.set_uniform_value('inset', floatValue(Math.min(this._inset, limit)));
        this.set_uniform_float('corners', 4, this._corners.map(radius => Math.min(radius, limit)));
        super.vfunc_paint_target(node, paintContext);
    }
});

/**
 * The blur behind one surface: a copy of what is behind it, cut to the shape of
 * the surface, blurred, and put right behind it.
 *
 * It is a sibling of the anchor rather than a child of the surface, because a
 * child would be painted over the surface's own color instead of under it. So
 * it follows the anchor by hand: where it is, and the small zoom and fade a
 * menu opens with.
 */
class Backdrop {
    constructor(shape, anchor, {onGone = null} = {}) {
        this._shape = shape;
        this._anchor = anchor;
        this._onGone = onGone;
        this._wanted = false;
        this._shown = false;
        this._updateId = 0;
        this._needsRestack = false;

        this._actor = new St.Widget({name: BACKDROP_NAME, clip_to_allocation: true, opacity: 0});
        this._content = this._desktopContent();
        this._actor.add_child(this._content);

        // The mask is added first so that it is applied to the blurred copy,
        // and not the other way round: an effect wraps those added after it.
        this._mask = new RoundedMaskEffect();
        this._blur = new Shell.BlurEffect({mode: Shell.BlurMode.ACTOR});
        this._actor.add_effect_with_name('mask', this._mask);
        this._actor.add_effect_with_name('blur', this._blur);

        anchor.get_parent().insert_child_below(this._actor, anchor);

        // Not the opacity: that is this backdrop's way of showing and hiding
        // itself, and it is the anchor's opacity only while it is shown.
        this._bindings = ['scale-x', 'scale-y', 'translation-x', 'translation-y']
            .map(property => anchor.bind_property(property, this._actor, property,
                GObject.BindingFlags.SYNC_CREATE));

        // A surface is moved in more ways than one: a menu is given a fixed
        // position, the bar is allocated, and the floating bar slides under its
        // own margin by a translation. Each of them is followed, as not all of
        // them change the allocation.
        const signals = [
            ...MOVED.map(signal => [shape, signal, () => this._place()]),
            ...MOVED.map(signal => [anchor, signal, () => this._place()]),
            [shape, 'notify::mapped', () => this.refresh()],
            [shape, 'style-changed', () => this.refresh()],
            [anchor, 'notify::visible', () => this._show()],
            [anchor, 'notify::opacity', () => this._show()],
        ];
        // The surface going is the one thing that has to be heard here rather
        // than from the UI group: once a menu has been destroyed its actors
        // cannot be touched at all any more, not even to disconnect from them.
        for (const object of new Set([shape, anchor]))
            signals.push([object, 'destroy', () => this._gone()]);

        this._signals = signals.map(([object, signal, callback]) =>
            [object, object.connect(signal, callback)]);

        this.refresh();
    }

    /** A copy of the desktop: the wallpaper and the windows, as they are now. */
    _desktopContent() {
        return new Clutter.Clone({source: global.window_group});
    }

    get anchor() {
        return this._anchor;
    }

    destroy() {
        const laters = global.compositor.get_laters();
        if (this._updateId) {
            laters.remove(this._updateId);
            this._updateId = 0;
        }
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = [];
        for (const binding of this._bindings)
            binding.unbind();
        this._bindings = [];
        this._actor.destroy();
        this._actor = null;
        this._content = null;
    }

    /** The surface is being destroyed, and takes its blur with it. */
    _gone() {
        const onGone = this._onGone;
        this._onGone = null;
        this.destroy();
        onGone?.();
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
        if (!this._wanted) {
            this._show();
            return;
        }

        this._blur.set({radius: Math.round(radius), brightness: hasBrightness ? brightness : 1});
        // The cut follows the surface's own outer edge. Insetting it by the
        // border instead was tried and is worse: the corner of the blur then
        // sits visibly inside the corner of the surface.
        this._mask.setShape(CORNERS.map(corner => node.get_border_radius(corner)), 0);
        this._place();
        this._show();
    }

    isShown() {
        return this._shown;
    }

    /**
     * Show or hide the blur by its opacity, and never by hiding the actor.
     *
     * An actor that has just been shown is waiting to be laid out, and Clutter
     * cannot say which of the stage's views it is on until it has been: it says
     * so in the log, and leaves the actor with no view and so with no way to
     * ask to be painted. It is given one again when it is next allocated, which
     * for a surface that keeps the same size and place, as the overview does,
     * may be never: the overview then comes up over a plain background and
     * stays that way until it is closed.
     *
     * At opacity zero the actor is laid out as always and simply not painted,
     * so it is always on a view and always ready to be shown again.
     */
    /** Where the shape sits inside the anchor, which may be a few actors up (a
     * menu's content is in a bin inside its box pointer) and may be sliding
     * (the floating bar docks by moving under its own margin). The anchor's own
     * scale and translation are left out: they are bound to the backdrop
     * instead, so that it is animated with the anchor.
     *
     * Every reading is of the allocation, never of x/y/width/height: those
     * answer with the size an actor would like to be, not the one it has, while
     * a relayout is pending. */
    _box() {
        const anchorBox = this._anchor.get_allocation_box();
        let x = anchorBox.x1;
        let y = anchorBox.y1;
        for (let actor = this._shape; actor && actor !== this._anchor; actor = actor.get_parent()) {
            const allocation = actor.get_allocation_box();
            x += allocation.x1 + actor.translation_x;
            y += allocation.y1 + actor.translation_y;
        }
        const box = this._shape.get_allocation_box();
        return [x, y, box.get_width(), box.get_height()];
    }

    _show() {
        const [, , width, height] = this._box();
        const ready = this._wanted && this._anchor.visible && width > 0 && height > 0;
        // A copy of the desktop is only drawn while the desktop itself is.
        const shown = ready && global.window_group.mapped;
        const opacity = shown ? this._anchor.opacity : 0;

        // Kept as a flag of its own, not read back from the actor: a menu that
        // is opening is shown at an opacity of nothing, and asking the actor
        // would never see it arrive.
        const wasShown = this._shown;
        this._shown = shown;
        this._actor.opacity = opacity;
        if (shown && !wasShown)
            this._place({restack: true});
    }

    /**
     * Moving and restacking the backdrop both wait for the frame's own moment
     * for such work, and are done once however much has been heard meanwhile.
     *
     * Most of what says a surface has moved is said while the Shell is laying
     * it out, and giving an actor a new size and place from inside that starts
     * another layout within the one going on. In the overview, where there is a
     * great deal to lay out, that showed as the app grid being painted several
     * times over, slightly out of step with itself.
     *
     * The moment is before the redraw, when the layout has been done and can be
     * read. Nothing is written back unless it has actually changed, so the
     * layout is undone only when the blur really has to move, and not once per
     * frame of an animation that leaves it where it was.
     *
     * A menu is also raised to the top of its parent as it opens, which would
     * leave its blur behind it; the raise is done once the menu has been shown,
     * so this has to follow it rather than lead it.
     */
    _place({restack = false} = {}) {
        this._needsRestack ||= restack;
        if (this._updateId)
            return;

        this._updateId = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._updateId = 0;
            const restackNow = this._needsRestack;
            this._needsRestack = false;
            this._placeNow();
            if (restackNow) {
                const parent = this._anchor.get_parent();
                if (parent && this._actor?.get_parent() === parent)
                    parent.set_child_below_sibling(this._actor, this._anchor);
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    _placeNow() {
        // A surface that has been taken off the stage without being destroyed
        // takes its blur with it: left behind, the blur goes on being laid out
        // in a branch that is no longer anywhere, which Clutter calls spurious
        // and says so every time something asks the branch for a size.
        if (!this._anchor.get_parent()) {
            this._gone();
            return;
        }

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
        const anchorBox = this._anchor.get_allocation_box();
        const [x, y, width, height] = this._box();

        // Only what has really changed is written back: setting an actor's size
        // and place undoes the layout, and a surface that is animated says it
        // has moved on every frame of it while staying exactly where it was.
        if (x !== this._actor.x || y !== this._actor.y)
            this._actor.set_position(x, y);
        if (width !== this._actor.width || height !== this._actor.height)
            this._actor.set_size(width, height);

        // Line the copy up with the screen it is a copy of
        const [stageX, stageY] = this._shape.get_transformed_position();
        if (-stageX !== this._content.x || -stageY !== this._content.y)
            this._content.set_position(-stageX, -stageY);

        // Zoom about the same point as the anchor, so that the blur follows the
        // way a menu opens instead of appearing at full size
        const pivot = this._anchor.pivot_point;
        this._actor.set_pivot_point(
            width > 0 ? (anchorBox.x1 + pivot.x * anchorBox.get_width() - x) / width : 0,
            height > 0 ? (anchorBox.y1 + pivot.y * anchorBox.get_height() - y) / height : 0);

        // A copy of the screen does not change by itself, so nothing else would
        // ask for it to be painted again at its new size and shape.
        this._actor.queue_redraw();
        this._show();
    }
}

const BACKGROUND_SCHEMA = 'org.gnome.desktop.background';
const INTERFACE_SCHEMA = 'org.gnome.desktop.interface';

// How GNOME's picture-options place a picture, as the stylesheet says it
const PLACEMENT = {
    zoom: 'background-size: cover; background-position: center;',
    spanned: 'background-size: cover; background-position: center;',
    scaled: 'background-size: contain; background-position: center;',
    stretched: 'background-size: 100% 100%;',
    centered: 'background-position: center;',
    wallpaper: 'background-position: 0 0;',
};

/**
 * What the overview is glass over, blurred: the wallpaper, one widget for each
 * monitor, behind the overview and in front of nothing else.
 *
 * It is the picture itself, drawn as any widget draws one. Copying the Shell's
 * own wallpaper actor into a blur was tried first, and that actor is not made
 * to be drawn into a buffer of somebody else's: what came out was a grey
 * background, the icons of an earlier frame, or the windows of the desktop.
 *
 * The widgets stay where they are and are shown by their opacity, never hidden
 * (see Backdrop._show), and the picture is loaded long before it is needed.
 * A wallpaper that is not a single picture (a slideshow) has no blur: it is
 * left to the Shell, and so to the overview's own color.
 */
class OverviewWallpaper {
    constructor() {
        this._widgets = [];
        this._shown = false;
        this._background = new Gio.Settings({schema_id: BACKGROUND_SCHEMA});
        this._interface = new Gio.Settings({schema_id: INTERFACE_SCHEMA});
        this._signals = [];
        for (const [settings, key] of [
            [this._background, 'changed'], [this._interface, 'changed::color-scheme']])
            this._signals.push([settings, settings.connect(key, () => this.rebuild())]);
        this.rebuild();
    }

    destroy() {
        for (const [settings, id] of this._signals)
            settings.disconnect(id);
        this._signals = [];
        this._drop();
    }

    _drop() {
        for (const widget of this._widgets)
            widget.destroy();
        this._widgets = [];
    }

    /** The widgets for the monitors and the picture there are now. */
    rebuild() {
        this._drop();
        const picture = this._style();
        if (!picture)
            return;
        const {style, spanned} = picture;

        // A spanned wallpaper is one picture over all the monitors together,
        // and each of them shows its own part of it, not all of it squeezed in.
        const monitors = Main.layoutManager.monitors;
        const left = Math.min(...monitors.map(monitor => monitor.x));
        const top = Math.min(...monitors.map(monitor => monitor.y));
        const right = Math.max(...monitors.map(monitor => monitor.x + monitor.width));
        const bottom = Math.max(...monitors.map(monitor => monitor.y + monitor.height));

        const uiGroup = Main.layoutManager.uiGroup;
        const overview = Main.layoutManager.overviewGroup;
        for (const monitor of monitors) {
            const widget = new St.Widget({
                name: BACKDROP_NAME,
                style: spanned ? `background-color: ${picture.color};` : style,
                x: monitor.x,
                y: monitor.y,
                width: monitor.width,
                height: monitor.height,
                clip_to_allocation: true,
                opacity: 0,
            });
            if (spanned) {
                // The whole picture, at the size of all the monitors, moved so
                // that this monitor's part of it is the part in view
                widget.add_child(new St.Widget({
                    style,
                    x: left - monitor.x,
                    y: top - monitor.y,
                    width: right - left,
                    height: bottom - top,
                }));
            }
            widget.add_effect_with_name('blur', new Shell.BlurEffect({mode: Shell.BlurMode.ACTOR}));
            uiGroup.insert_child_below(widget, overview);
            this._widgets.push(widget);
        }
        if (this._shown)
            this.show();
    }

    _style() {
        const dark = this._interface.get_string('color-scheme') === 'prefer-dark';
        let uri = dark ? this._background.get_string('picture-uri-dark') : '';
        uri ||= this._background.get_string('picture-uri');
        const options = this._background.get_string('picture-options');
        const color = this._background.get_string('primary-color') || '#000000';

        let style = `background-color: ${color};`;
        if (options !== 'none') {
            // A slideshow is an XML file listing pictures, not a picture
            if (!uri || uri.endsWith('.xml'))
                return null;
            style += ` background-image: url("${uri}"); ${PLACEMENT[options] ?? PLACEMENT.zoom}`;
        }
        return {style, color, spanned: options === 'spanned'};
    }

    show() {
        this._shown = true;
        const overview = Main.layoutManager.overviewGroup;
        if (!overview.mapped)
            return;

        const node = overview.get_theme_node();
        const [hasRadius, radius] = node.lookup_length(RADIUS_PROPERTY, false);
        const [hasBrightness, brightness] = node.lookup_double(BRIGHTNESS_PROPERTY, false);
        const wanted = hasRadius && radius > 0;

        const uiGroup = Main.layoutManager.uiGroup;
        for (const widget of this._widgets) {
            widget.get_effect('blur').set({
                radius: Math.round(radius),
                brightness: hasBrightness ? brightness : 1,
            });
            // Kept right behind the overview, whatever has been added since
            uiGroup.set_child_below_sibling(widget, overview);
            widget.opacity = wanted ? 255 : 0;
        }
    }

    hide() {
        this._shown = false;
        for (const widget of this._widgets)
            widget.opacity = 0;
    }
}

export default class BlurExtension extends Extension {
    enable() {
        this._backdrops = new Set();   // one for each surface
        this._wallpaper = new OverviewWallpaper();   // what the overview is glass over
        this._signals = [];

        const uiGroup = Main.layoutManager.uiGroup;
        this._connect(uiGroup, 'child-added', (_group, actor) => this._watch(actor));
        this._connect(uiGroup, 'child-removed', (_group, actor) => this._unwatch(actor));
        // The desktop is hidden while the overview is open, and a copy of it is
        // only worth drawing while it is not.
        this._connect(global.window_group, 'notify::mapped', () => this._showAll());
        // The overview is shown and hidden without being moved or resized, so
        // little is said about it; and it is the one surface other extensions
        // take a hand in. Asking it again as it opens costs a theme node and
        // keeps it from standing on whichever signal happened to arrive.
        // The theme is reloaded whole whenever the style or the accent changes,
        // and for a moment carries none of this project's properties. Every
        // surface is asked again once it has settled.
        this._connect(St.ThemeContext.get_for_stage(global.stage), 'changed',
            () => this._refreshAll());
        this._connect(Main.overview, 'showing', () => {
            this._refreshAll();
            this._wallpaper.show();
        });
        this._connect(Main.overview, 'shown', () => this._wallpaper.show());
        this._connect(Main.overview, 'hidden', () => this._wallpaper.hide());
        this._connect(Main.layoutManager, 'monitors-changed', () => this._wallpaper.rebuild());

        for (const actor of uiGroup.get_children())
            this._watch(actor);
    }

    disable() {
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = null;

        for (const backdrop of this._backdrops)
            backdrop.destroy();
        this._backdrops = null;
        this._wallpaper.destroy();
        this._wallpaper = null;
    }

    _connect(object, signal, callback) {
        this._signals.push([object, object.connect(signal, callback)]);
    }

    // Everything the theme may have asked to blur is in the UI group: the top
    // bar, the overview, menus as they are created, and the dock of Dash to
    // Dock.
    _watch(actor) {
        if (actor.name === BACKDROP_NAME)
            return;
        if (actor === Main.layoutManager.panelBox) {
            this._add(Main.panel, actor);
            return;
        }
        // The overview is not given a surface of its own: its wallpaper is
        // blurred instead, as it opens.
        if (actor === Main.layoutManager.overviewGroup)
            return;
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
        for (const backdrop of [...this._backdrops]) {
            if (backdrop.anchor === actor || backdrop.anchor.get_parent() === actor) {
                this._backdrops.delete(backdrop);
                backdrop.destroy();
            }
        }
    }

    _add(shape, anchor) {
        if (!anchor || !anchor.get_parent() || this._find(anchor))
            return;
        const backdrop = new Backdrop(shape, anchor,
            {onGone: () => this._backdrops.delete(backdrop)});
        this._backdrops.add(backdrop);
    }

    _find(anchor) {
        for (const backdrop of this._backdrops) {
            if (backdrop.anchor === anchor)
                return backdrop;
        }
        return null;
    }

    _showAll() {
        for (const backdrop of this._backdrops)
            backdrop._show();
    }

    _refreshAll() {
        for (const backdrop of this._backdrops)
            backdrop.refresh();
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
