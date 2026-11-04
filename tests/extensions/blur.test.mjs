import assert from 'node:assert/strict';
import {test} from 'node:test';

import {loadExtension} from './load.mjs';
import {Actor, Main, backdropsIn, desktop, gsettings, menu, settle, state, themeContext} from './blur.mocks.mjs';

const Blur = await loadExtension('blur@gattuccino', 'blur.mocks.mjs');

const THEME = {radius: 32, brightness: 1, alpha: 204, corners: [16, 16, 16, 16], border: 0};
const reset = () => { state.theme = {...THEME}; };

/** The blur shows and hides itself by its opacity, never by hiding the actor:
 * an actor that has just been shown has no allocation, and Clutter then cannot
 * say which of the stage's views it is on. */
const shown = backdrop => backdrop.opacity > 0;

/** The backdrop the extension put right behind `anchor`, if any. */
function backdropOf(anchor) {
    const siblings = anchor.get_parent().get_children();
    const before = siblings[siblings.indexOf(anchor) - 1];
    return before?.name === 'gattuccino-blur' ? before : null;
}

test('the top bar', async t => {
    reset();
    const {panelBox, panel, uiGroup} = desktop();
    const extension = new Blur();
    extension.enable();
    const backdrop = backdropOf(panelBox);

    await t.test('puts a copy of the desktop behind the bar, and nowhere else', () => {
        assert.ok(backdrop, 'no backdrop');
        assert.equal(backdrop.get_parent(), uiGroup);
        // Behind the bar, so that the color of the bar is drawn over it
        assert.equal(uiGroup.get_children().indexOf(backdrop), uiGroup.get_children().indexOf(panelBox) - 1);
        assert.equal(backdrop.get_children()[0].source, global.window_group);
        // the bar's and the overview's wallpaper, and nothing else
        assert.equal(backdropsIn(uiGroup).length, 2);
    });

    await t.test('covers exactly the bar', () => {
        settle();   // the backdrop is placed at the end of the frame, never in the middle of one
        assert.deepEqual([backdrop.x, backdrop.y, backdrop.width, backdrop.height], [6, 6, 1588, 32]);
        // The copy is lined up with the screen it is a copy of
        assert.deepEqual(backdrop.get_children()[0].get_size ? [backdrop.get_children()[0].x, backdrop.get_children()[0].y] : [], [-6, -6]);
    });

    await t.test('takes the blur from the theme', () => {
        assert.equal(backdrop.get_effect('blur').radius, 32);
        assert.equal(backdrop.get_effect('blur').brightness, 1);
        assert.equal(backdrop.get_effect('blur').mode, 0);   // of the actor it is given, not of the screen

    });

    await t.test('cuts it to the corners of the bar', () => {
        settle();
        const mask = backdrop.get_effect('mask');
        mask.get_actor = () => backdrop;
        mask.vfunc_paint_target(null, null);
        assert.deepEqual(mask.uniforms.corners.values, [16, 16, 16, 16]);

        // The shape is measured in the pixels of the copy it is painted
        // through, which is a little larger than the bar, with the bar's own
        // size given separately: measured in the bar's own pixels, its corners
        // would be stretched by the difference.
        assert.deepEqual(mask.uniforms.size.values, [1588, 32]);
        assert.deepEqual(mask.uniforms.offscreen.values, [1591, 35]);

        // Never more than half the smaller side, or the shape would fold over
        state.theme = {...THEME, corners: [999, 999, 999, 999]};
        panel.emit('style-changed');
        settle();
        mask.vfunc_paint_target(null, null);
        assert.deepEqual(mask.uniforms.corners.values, [16, 16, 16, 16]);
        reset();
        panel.emit('style-changed');
    });

    await t.test('follows the bar as it slides between floating and docked', () => {
        panel.translation_y = -6;
        panel.emit('notify::translation-y');
        settle();
        assert.deepEqual([backdrop.x, backdrop.y], [6, 0]);
        panel.translation_y = 0;
        panel.emit('notify::translation-y');
        settle();
        assert.deepEqual([backdrop.x, backdrop.y], [6, 6]);

        panel.set_size(1600, 32);
        panel.set_position(0, 0);
        settle();
        assert.deepEqual([backdrop.x, backdrop.y, backdrop.width], [0, 0, 1600]);
        panel.set_position(6, 6);
        panel.set_size(1588, 32);
        settle();
    });

    // Most of what says a surface has moved is said while the Shell is laying
    // it out, and moving an actor from inside that lays out again within the
    // layout going on, which the overview showed as the app grid painted
    // several times over, slightly out of step with itself.
    await t.test('is never moved in the middle of a layout', () => {
        panel.set_position(10, 12);
        assert.deepEqual([backdrop.x, backdrop.y], [6, 6], 'moved while the bar was being laid out');

        settle();
        assert.deepEqual([backdrop.x, backdrop.y], [10, 12]);
        panel.set_position(6, 6);
        settle();
    });

    await t.test('steps aside while the bar is solid, as nothing shows through it', () => {
        state.theme = {...THEME, alpha: 255};
        panel.emit('style-changed');
        assert.equal(shown(backdrop), false);

        // and while it has no background at all, as in the overview
        state.theme = {...THEME, alpha: 0};
        panel.emit('style-changed');
        assert.equal(shown(backdrop), false);

        reset();
        panel.emit('style-changed');
        assert.equal(shown(backdrop), true);
    });

    // The theme is reloaded whole when the style or the accent changes, and
    // carries none of these properties while it is between the two.
    await t.test('comes back after the theme has been reloaded', () => {
        state.theme = {...THEME, radius: null};
        panel.emit('style-changed');
        assert.equal(shown(backdrop), false);

        reset();                       // the new theme is in place, unsaid
        themeContext.emit('changed');
        settle();
        assert.equal(shown(backdrop), true);
    });

    await t.test('does nothing at all with a theme that does not ask for it', () => {
        state.theme = {...THEME, radius: null};
        panel.emit('style-changed');
        assert.equal(shown(backdrop), false);
        reset();
        panel.emit('style-changed');
        assert.equal(shown(backdrop), true);
    });

    await t.test('hides with the bar', () => {
        panelBox.set({visible: false});
        assert.equal(shown(backdrop), false);
        panelBox.set({visible: true});
        assert.equal(shown(backdrop), true);
    });

    await t.test('takes everything of its own away again on disable', () => {
        extension.disable();
        assert.equal(backdropsIn(uiGroup).length, 0);
        assert.equal(backdrop.destroyed, true);
        assert.equal(panel.handlerCount, 0);
        assert.equal(panelBox.handlerCount, 0);
        assert.equal(uiGroup.handlerCount, 0);
    });
});

test('menus', async t => {
    reset();
    const {uiGroup} = desktop();
    const extension = new Blur();
    extension.enable();

    await t.test('are blurred whether they are in the UI group on their own or wrapped', () => {
        for (const wrapped of [false, true]) {
            const {top, pointer, content} = menu({wrapped});
            uiGroup.add_child(top);

            settle();
            const backdrop = backdropOf(pointer);
            assert.ok(backdrop, `no backdrop (wrapped: ${wrapped})`);
            // A sibling of the box pointer: it is what the menu is animated by
            assert.equal(backdrop.get_parent(), pointer.get_parent());
            // Over the content, which sits 6px down inside the box pointer
            assert.deepEqual([backdrop.x, backdrop.y], [100, 46], `wrapped: ${wrapped}`);
            assert.deepEqual([backdrop.width, backdrop.height], [400, 300]);
        }
    });

    await t.test('are zoomed and faded with the menu as it opens', () => {
        const {top, pointer} = menu({wrapped: false});
        uiGroup.add_child(top);
        const backdrop = backdropOf(pointer);

        pointer.pivot_point = {x: 0.5, y: 0};
        pointer.set({opacity: 0, scale_x: 0.96, scale_y: 0.96, translation_y: -6});
        settle();
        assert.equal(backdrop.opacity, 0);
        assert.equal(backdrop.scale_x, 0.96);
        assert.equal(backdrop.translation_y, -6);

        // The same point on screen as the menu's own, which is half a step up
        // and across from the backdrop's own corner
        assert.equal(backdrop.pivot_point.x, (100 + 0.5 * 400 - 100) / 400);
        assert.ok(backdrop.pivot_point.y < 0);

        pointer.set({opacity: 255, scale_x: 1, scale_y: 1, translation_y: 0});
        assert.equal(backdrop.opacity, 255);
    });

    await t.test('are not shown before they have been given a size', () => {
        const {top, pointer, content} = menu({width: 0, height: 0});
        uiGroup.add_child(top);
        settle();
        const backdrop = backdropOf(pointer);
        assert.equal(shown(backdrop), false, 'shown before it had a size');

        content.set_size(400, 300);
        settle();
        assert.equal(shown(backdrop), true);
    });

    await t.test('wait for their first opening, when they have a style to read', () => {
        const {top, pointer, content} = menu();
        content.mapped = false;
        uiGroup.add_child(top);
        const backdrop = backdropOf(pointer);
        assert.equal(shown(backdrop), false);

        content.mapped = true;
        content.emit('notify::mapped');
        assert.equal(shown(backdrop), true);
        assert.equal(backdrop.get_effect('blur').radius, 32);
    });

    await t.test('keep it right behind them when they are raised on opening', () => {
        const {top, pointer, content} = menu();
        content.mapped = false;
        uiGroup.add_child(top);
        const backdrop = backdropOf(pointer);
        const indexes = () => [uiGroup.get_children().indexOf(backdrop), uiGroup.get_children().indexOf(top)];

        uiGroup.add_child(new Actor({name: 'somethingAbove'}));

        // The Shell shows a menu and then puts it on top of everything else
        content.mapped = true;
        content.emit('notify::mapped');
        uiGroup.set_child_above_sibling(top, null);
        const [behind, menuAt] = indexes();
        assert.notEqual(behind, menuAt - 1, 'the blur was expected to be left behind');

        settle();
        const [after, raised] = indexes();
        assert.equal(after, raised - 1);
    });

    await t.test('take their blur away with them when they are taken out', () => {
        const {top, pointer} = menu();
        uiGroup.add_child(top);
        const backdrop = backdropOf(pointer);
        assert.ok(backdrop);

        uiGroup.remove_child(top);
        assert.equal(backdrop.destroyed, true);
        assert.equal(pointer.handlerCount, 0);
    });

    // A menu that has been destroyed cannot be touched again at all, not even
    // to disconnect from it: the blur has to be taken down while it is still
    // alive, which is what its 'destroy' says.
    // Clutter goes on laying out a branch that has been taken off the stage,
    // and complains about every actor in it that is not its own.
    await t.test('take their blur away with them when they are taken off the stage', () => {
        const {top, pointer} = menu();
        uiGroup.add_child(top);
        settle();
        const backdrop = backdropOf(pointer);
        assert.ok(backdrop);

        top._parent = null;        // off the stage, without a word to the UI group
        pointer.set_position(1, 1);
        settle();
        assert.equal(backdrop.destroyed, true);
    });

    await t.test('take their blur away with them when they are destroyed', () => {
        const {top, pointer} = menu();
        uiGroup.add_child(top);
        const backdrop = backdropOf(pointer);
        assert.ok(backdrop);

        top.destroy();   // throws if anything of it is used afterwards
        assert.equal(backdrop.destroyed, true);

        // and the menu is forgotten, so that nothing reaches for it later: this
        // is what used to throw, once per menu, for the rest of the session
        const other = new Actor({name: 'later'});
        uiGroup.add_child(other);
        uiGroup.remove_child(other);
    });

    extension.disable();
});

test('the overview', async t => {
    reset();
    const {uiGroup, overviewGroup} = desktop();
    const extension = new Blur();
    extension.enable();
    const wallpapers = () => backdropsIn(uiGroup).filter(widget => widget.style);
    const open = () => {
        overviewGroup.set({visible: true});
        overviewGroup.mapped = true;
        Main.overview.emit('showing');
    };

    await t.test('has the wallpaper of each monitor right behind it, unseen until it opens', () => {
        assert.equal(wallpapers().length, 1);
        const [wallpaper] = wallpapers();
        const siblings = uiGroup.get_children();
        assert.equal(siblings.indexOf(wallpaper), siblings.indexOf(overviewGroup) - 1);
        assert.deepEqual([wallpaper.x, wallpaper.y, wallpaper.width, wallpaper.height], [0, 0, 1600, 900]);
        assert.match(wallpaper.style, /background-image: url\("file:\/\/\/usr\/share\/backgrounds\/wall.jpg"\)/);
        assert.match(wallpaper.style, /background-size: cover/);
        assert.equal(wallpaper.opacity, 0);
    });

    await t.test('is blurred and shown as the overview opens', () => {
        open();
        const [wallpaper] = wallpapers();
        assert.equal(wallpaper.opacity, 255);
        assert.equal(wallpaper.get_effect('blur').radius, 32);
        assert.equal(wallpaper.get_effect('blur').mode, 0);
    });

    await t.test('goes again once it has closed', () => {
        Main.overview.emit('hidden');
        assert.equal(wallpapers()[0].opacity, 0);
    });

    await t.test('is not shown when the theme does not ask for a blur', () => {
        state.theme = {...THEME, radius: null};
        open();
        assert.equal(wallpapers()[0].opacity, 0);
        Main.overview.emit('hidden');
        reset();
    });

    await t.test('follows the monitors, one each', () => {
        Main.layoutManager.monitors = [
            {index: 0, x: 0, y: 0, width: 1600, height: 900},
            {index: 1, x: 1600, y: 0, width: 1280, height: 1024},
        ];
        Main.layoutManager.emit('monitors-changed');
        assert.equal(wallpapers().length, 2);
        assert.deepEqual([wallpapers()[1].x, wallpapers()[1].width], [1600, 1280]);
    });

    await t.test('shows each monitor its own part of a spanned wallpaper', () => {
        gsettings['picture-options'] = 'spanned';
        Main.layoutManager.emit('monitors-changed');
        const [first, second] = wallpapers();
        for (const [wallpaper, monitor] of [[first, 0], [second, 1]]) {
            const [picture] = wallpaper.get_children();
            assert.match(picture.style, /wall.jpg/);
            assert.deepEqual([picture.width, picture.height], [2880, 1024]);
            assert.deepEqual([picture.x, picture.y], [monitor ? -1600 : 0, 0]);
        }
        gsettings['picture-options'] = 'zoom';
    });

    await t.test('has none for a wallpaper that is a slideshow', () => {
        gsettings['picture-uri'] = 'file:///usr/share/backgrounds/slides.xml';
        Main.layoutManager.emit('monitors-changed');
        assert.equal(wallpapers().length, 0);
        gsettings['picture-uri'] = 'file:///usr/share/backgrounds/wall.jpg';
    });

    await t.test('takes the dark picture when the style is dark', () => {
        gsettings['color-scheme'] = 'prefer-dark';
        Main.layoutManager.emit('monitors-changed');
        assert.match(wallpapers()[0].style, /wall-dark.jpg/);
        gsettings['color-scheme'] = 'default';
    });

    await t.test('is given up on disable', () => {
        extension.disable();
        assert.equal(backdropsIn(uiGroup).length, 0);
    });
});

test('a copy of the desktop', async t => {
    reset();
    const {uiGroup, windowGroup, panelBox} = desktop();
    const extension = new Blur();
    extension.enable();
    const siblings = () => uiGroup.get_children();
    const bar = siblings()[siblings().indexOf(panelBox) - 1];

    await t.test('is not drawn while the desktop itself is not', () => {
        assert.equal(shown(bar), true);

        // What the Shell does while the overview is open
        windowGroup.set({mapped: false});
        assert.equal(shown(bar), false);

        windowGroup.set({mapped: true});
        assert.equal(shown(bar), true);
    });

    extension.disable();
});

test('the dock', async t => {
    reset();
    const {uiGroup} = desktop();
    const extension = new Blur();
    extension.enable();

    await t.test('is blurred under its background, inside its own container', () => {
        const container = new Actor({name: 'dashtodockContainer', x: 500, y: 800});
        const dash = new Actor({name: 'dash'});
        const background = new Actor({x: 4, y: 2, width: 600, height: 80, style_class: 'dash-background'});
        dash.add_child(background);
        container.add_child(dash);
        uiGroup.add_child(container);

        settle();
        const backdrop = backdropOf(container);
        assert.ok(backdrop, 'no backdrop');
        assert.deepEqual([backdrop.x, backdrop.y, backdrop.width, backdrop.height], [504, 802, 600, 80]);
    });

    await t.test('is left alone when Dash to Dock is not there', () => {
        const other = new Actor({name: 'somethingElse'});
        uiGroup.add_child(other);
        assert.equal(backdropsIn(other).length, 0);
    });

    extension.disable();
});
