import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GdkPixbuf from 'gi://GdkPixbuf';
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

/**
 * How GNOME's picture-options place a picture in a box, as the stylesheet says
 * it: the size of the picture and where its corner is, in pixels. The
 * stylesheet has keywords for this (cover, contain, center) and the Shell does
 * not read all of them, so it is worked out here from the size of the picture.
 */
function placement(options, [width, height], size) {
    const style = (w, h, x, y) =>
        `background-size: ${Math.round(w)}px ${Math.round(h)}px; ` +
        `background-position: ${Math.round(x)}px ${Math.round(y)}px;`;
    if (options === 'stretched' || !size)
        return `background-size: ${width}px ${height}px; background-position: 0px 0px;`;

    const [w, h] = size;
    const fit = options === 'scaled' ? Math.min(width / w, height / h)
        : options === 'centered' || options === 'wallpaper' ? 1
            : Math.max(width / w, height / h);          // zoom, spanned and the others
    const [shownWidth, shownHeight] = [w * fit, h * fit];
    return options === 'wallpaper'
        ? style(shownWidth, shownHeight, 0, 0)
        : style(shownWidth, shownHeight, (width - shownWidth) / 2, (height - shownHeight) / 2);
}

function pictureStyle(picture, box) {
    let style = `background-color: ${picture.color};`;
    if (picture.uri)
        style += ` background-image: url("${picture.uri}"); ${placement(picture.options, box, picture.size)}`;
    return style;
}

/** The size of a picture in pixels, read from its header, or null */
function pictureSize(uri) {
    try {
        const path = Gio.File.new_for_uri(uri).get_path();
        const [format, width, height] = GdkPixbuf.Pixbuf.get_file_info(path);
        return format && width > 0 && height > 0 ? [width, height] : null;
    } catch (e) {
        return null;
    }
}

/** A color of the settings, which are written as #rrggbb or as #rrrrggggbbbb,
 * in the form a stylesheet understands */
function cssColor(text) {
    const digits = /^#([0-9a-f]{12})$/i.exec(text ?? '')?.[1];
    if (digits)
        return `#${digits.slice(0, 2)}${digits.slice(4, 6)}${digits.slice(8, 10)}`;
    return /^#[0-9a-f]{6}$/i.test(text ?? '') ? text : '#000000';
}

/**
 * The wallpaper as the desktop background settings describe it: the picture
 * to draw and how, or null when it is not a single picture (a slideshow is an
 * XML file listing pictures), which is then left to the Shell.
 */
class WallpaperSettings {
    constructor(onChanged) {
        this._background = new Gio.Settings({schema_id: BACKGROUND_SCHEMA});
        this._interface = new Gio.Settings({schema_id: INTERFACE_SCHEMA});
        this._signals = [];
        for (const [settings, key] of [
            [this._background, 'changed'], [this._interface, 'changed::color-scheme']])
            this._signals.push([settings, settings.connect(key, onChanged)]);
    }

    destroy() {
        for (const [settings, id] of this._signals)
            settings.disconnect(id);
        this._signals = [];
    }

    picture() {
        const dark = this._interface.get_string('color-scheme') === 'prefer-dark';
        let uri = dark ? this._background.get_string('picture-uri-dark') : '';
        uri ||= this._background.get_string('picture-uri');
        const options = this._background.get_string('picture-options');
        const color = cssColor(this._background.get_string('primary-color'));

        if (options === 'none')
            return {uri: null, options, color, size: null, spanned: false};
        // A slideshow is an XML file listing pictures, not a picture
        if (!uri || uri.endsWith('.xml'))
            return null;
        return {uri, options, color, size: pictureSize(uri), spanned: options === 'spanned'};
    }
}

/**
 * Draw the wallpaper in a widget that is the size of one monitor.
 *
 * A spanned wallpaper is one picture over all the monitors together, and each
 * of them shows its own part of it, not all of it squeezed in: the widget then
 * holds the whole picture at the size of all the monitors, moved so that this
 * monitor's part is the part in view.
 */
function drawWallpaper(widget, monitor, picture) {
    const monitors = Main.layoutManager.monitors;
    if (!picture.spanned) {
        widget.style = pictureStyle(picture, [monitor.width, monitor.height]);
        return;
    }

    const left = Math.min(...monitors.map(each => each.x));
    const top = Math.min(...monitors.map(each => each.y));
    const right = Math.max(...monitors.map(each => each.x + each.width));
    const bottom = Math.max(...monitors.map(each => each.y + each.height));
    widget.style = `background-color: ${picture.color};`;
    widget.add_child(new St.Widget({
        style: pictureStyle(picture, [right - left, bottom - top]),
        x: left - monitor.x,
        y: top - monitor.y,
        width: right - left,
        height: bottom - top,
    }));
}

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
    constructor(settings) {
        this._widgets = [];
        this._shown = false;
        this._settings = settings;
        this.rebuild();
    }

    destroy() {
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
        const picture = this._settings.picture();
        if (!picture)
            return;

        const uiGroup = Main.layoutManager.uiGroup;
        const overview = Main.layoutManager.overviewGroup;
        for (const monitor of Main.layoutManager.monitors) {
            const widget = new St.Widget({
                name: BACKDROP_NAME,
                x: monitor.x,
                y: monitor.y,
                width: monitor.width,
                height: monitor.height,
                clip_to_allocation: true,
                opacity: 0,
            });
            drawWallpaper(widget, monitor, picture);
            widget.add_effect_with_name('blur', new Shell.BlurEffect({mode: Shell.BlurMode.ACTOR}));
            uiGroup.insert_child_below(widget, overview);
            this._widgets.push(widget);
        }
        if (this._shown)
            this.show();
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

/**
 * The wallpaper behind the lock screen, the same as the desktop's, each
 * monitor with its own part of it: the clock and the password prompt are
 * two pages of one dialog, and share one background of blurred wallpapers, one
 * widget for each monitor, which the Shell blurs itself.
 *
 * The Shell fills those widgets with its own wallpaper actor, which is the
 * thing that is not made to be drawn into a blur: the clock page comes up
 * well enough and the prompt page comes up black. They are given the picture
 * instead, drawn as the overview's is, and the Shell's own blur, radius and
 * dimming are left as they are.
 */
class LockWallpaper {
    constructor(settings) {
        this._settings = settings;
        // How far the theme blurs the lock screen's wallpaper, 0 for not at
        // all, or null when it is not known. It is read while the desktop is
        // up: the lock screen runs with GNOME's own stylesheet, with none of
        // this theme's rules in it.
        this.radius = null;
        this._dressed = new Set();   // [widget, [what was hidden], [what was added]]
        this._signals = [];
        this._idles = new Set();

        const shield = Main.screenShield;
        const group = shield?._lockDialogGroup;
        if (!group)
            return;
        // The dialog is made each time the screen is locked, and its
        // background is made a moment after it is added to this group.
        this._connect(group, 'child-added', (_group, dialog) => this._later(() => this._watch(dialog)));
        if (shield._dialog)
            this._watch(shield._dialog);
    }

    destroy() {
        for (const id of this._idles)
            GLib.Source.remove(id);
        this._idles.clear();
        for (const [object, id] of this._signals) {
            try {
                object.disconnect(id);
            } catch (e) {
                // already gone with the dialog
            }
        }
        this._signals = [];
        this._undress();
    }

    _connect(object, signal, callback) {
        this._signals.push([object, object.connect(signal, callback)]);
    }

    _later(callback) {
        const id = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._idles.delete(id);
            callback();
            return GLib.SOURCE_REMOVE;
        });
        this._idles.add(id);
    }

    _watch(dialog) {
        const group = dialog._backgroundGroup;
        if (!group)
            return;
        for (const widget of group.get_children())
            this._dress(widget);
        // The Shell makes them again when the monitors change
        this._connect(group, 'child-added', (_group, widget) => this._later(() => this._dress(widget)));
    }

    _dress(widget) {
        const picture = this._settings.picture();
        if (!picture || [...this._dressed].some(([dressed]) => dressed === widget))
            return;
        const monitor = Main.layoutManager.monitors.find(each => each.x === widget.x && each.y === widget.y);
        if (!monitor)
            return;

        // Whether the theme asks for it, and how far, is said on the widget
        // itself; with another theme, or with the background blur turned off,
        // the lock screen is left exactly as the Shell makes it.
        let radius = this.radius;
        if (radius === null) {
            const [has, asked] = widget.get_theme_node().lookup_length(RADIUS_PROPERTY, false);
            radius = has ? asked : 0;
        }
        if (radius <= 0)
            return;

        // What the Shell put in the widget is hidden and not taken out, so
        // that it is as it was found when this is turned off
        const hidden = widget.get_children();
        for (const child of hidden)
            child.hide();
        drawWallpaper(widget, monitor, picture);
        const added = widget.get_children().filter(child => !hidden.includes(child));

        // The Shell blurs its lock screen by 90 pixels; the theme says how far
        // it is to be blurred, and its dimming is the Shell's own.
        const effect = widget.get_effect('blur');
        const was = effect ? {radius: effect.radius} : null;
        if (effect)
            effect.set({radius: Math.round(radius)});
        this._dressed.add([widget, hidden, added, was]);
    }

    /** The wallpaper was changed while the screen is locked */
    refresh() {
        const widgets = [...this._dressed].map(([widget]) => widget);
        this._undress();
        for (const widget of widgets) {
            try {
                this._dress(widget);
            } catch (e) {
                // the widget has gone with the dialog
            }
        }
    }

    _undress() {
        for (const [widget, hidden, added, was] of this._dressed) {
            try {
                if (was)
                    widget.get_effect('blur')?.set(was);
                for (const child of added)
                    child.destroy();
                for (const child of hidden)
                    child.show();
                widget.style = '';
            } catch (e) {
                // the widget has gone with the dialog
            }
        }
        this._dressed.clear();
    }
}

export default class BlurExtension extends Extension {
    enable() {
        this._backdrops = new Set();   // one for each surface
        // One reading of the wallpaper for both places it is drawn
        this._settings = new WallpaperSettings(() => {
            this._wallpaper?.rebuild();
            this._lock?.refresh();
        });
        this._wallpaper = new OverviewWallpaper(this._settings);   // what the overview is glass over
        this._lock = new LockWallpaper(this._settings);
        this._signals = [];

        const uiGroup = Main.layoutManager.uiGroup;
        // A widget of the lock screen's kind, kept out of sight, to read what
        // the theme says about it
        this._probe = new St.Widget({
            name: 'gattuccino-probe', style_class: 'screen-shield-background',
            width: 1, height: 1, opacity: 0, reactive: false,
        });
        uiGroup.add_child(this._probe);
        this._readLockRadius();
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
        this._connect(St.ThemeContext.get_for_stage(global.stage), 'changed', () => {
            this._refreshAll();
            this._readLockRadius();
        });
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
        this._lock.destroy();
        this._lock = null;
        this._probe.destroy();
        this._probe = null;
        this._settings.destroy();
        this._settings = null;
    }

    _connect(object, signal, callback) {
        this._signals.push([object, object.connect(signal, callback)]);
    }

    // Not while the screen is locked: the stylesheet is then GNOME's own, and
    // would say the theme asks for nothing.
    _readLockRadius() {
        if (Main.sessionMode?.isLocked || !this._probe?.mapped)
            return;
        const [has, radius] = this._probe.get_theme_node().lookup_length(RADIUS_PROPERTY, false);
        this._lock.radius = has && radius > 0 ? Math.round(radius) : 0;
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
