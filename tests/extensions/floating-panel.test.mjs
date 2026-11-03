import assert from 'node:assert/strict';
import {test} from 'node:test';

import {loadExtension} from './load.mjs';
import {Main, Meta, Window, pendingIdle, settle, state, workspace} from './floating-panel.mocks.mjs';

const FloatingPanel = await loadExtension('floating-panel@gattuccino', 'floating-panel.mocks.mjs');

const PANEL = 32, GAP = 6;
const classes = () => [...Main.panel.classes].sort().join(' ');
// While enabled the panel is always in exactly one of the two states
const floating = () => {
    assert.ok(['floating-panel', 'docked-panel'].includes(classes()), `classes: "${classes()}"`);
    return classes() === 'floating-panel';
};
function open(window) {
    const actor = new Meta.WindowActor();
    workspace.windows.push(window);
    global.actors.push(actor);
    global.window_group.emit('child-added', actor);
    return actor;
}
function moved(actor) { actor.emit('notify::allocation'); settle(); }
const margins = () => [Main.panel.margin_top, Main.panel.margin_left, Main.panel.margin_right];

test('floating panel', async t => {
    const extension = new FloatingPanel();
    extension.enable();
    const window = new Window({y: 300});
    const actor = open(window);
    settle();

    await t.test('floats on an empty desktop and with windows far away', () => {
        assert.equal(floating(), true);
        window.y = PANEL + 20; moved(actor);
        assert.equal(floating(), true);
    });

    await t.test('docks when a window comes close, in one coalesced update', () => {
        window.y = PANEL + 15;
        actor.emit('notify::allocation'); actor.emit('notify::allocation');
        assert.equal(pendingIdle(), 1);
        settle();
        assert.equal(floating(), false);
    });

    await t.test('does not flip back and forth under a maximized window', () => {
        window.y = 300; moved(actor);
        assert.equal(floating(), true);
        window.y = PANEL + GAP; moved(actor);   // maximized below the floating gap
        assert.equal(floating(), false);
        window.y = PANEL;                       // the work area grew once docked
        for (let i = 0; i < 5; i++) { moved(actor); assert.equal(floating(), false); }
    });

    await t.test('ignores minimized windows, other monitors, desktop windows and desktop icons', () => {
        window.minimized = true; actor.emit('notify::visible'); settle(); assert.equal(floating(), true);
        window.minimized = false; actor.emit('notify::visible'); settle(); assert.equal(floating(), false);
        window.monitor = 1; moved(actor); assert.equal(floating(), true);
        window.monitor = 0; window.type = Meta.WindowType.DESKTOP; moved(actor); assert.equal(floating(), true);
        window.type = Meta.WindowType.NORMAL; window.app = 'com.rastersoft.ding'; moved(actor); assert.equal(floating(), true);
        window.app = 'org.gnome.Nautilus'; moved(actor); assert.equal(floating(), false);
    });

    await t.test('follows workspace switches', () => {
        const windows = workspace.windows;
        workspace.windows = []; global.workspace_manager.emit('active-workspace-changed'); settle();
        assert.equal(floating(), true);
        workspace.windows = windows; global.workspace_manager.emit('active-workspace-changed'); settle();
        assert.equal(floating(), false);
    });

    await t.test('scales the distance on HiDPI screens', () => {
        state.scale = 2; Main.panel.height = 64;
        window.y = 64 + 31; Main.panel.emit('notify::height'); settle(); assert.equal(floating(), false);
        window.y = 64 + 33; moved(actor); assert.equal(floating(), true);
        state.scale = 1; Main.panel.height = PANEL; window.y = PANEL; moved(actor);
    });

    await t.test('floats again when the window closes, without touching the destroyed actor', () => {
        workspace.windows = []; global.actors = [];
        actor.emit('destroy'); global.window_group.emit('child-removed', actor); settle();
        assert.equal(floating(), true);
        assert.equal(actor.handlerCount, 3);
    });

    await t.test('ignores children of the window group that are not windows', () => {
        global.window_group.emit('child-added', {connect() { throw new Error('connected to a non-window'); }});
    });

    await t.test('cleans up on disable, even with an update pending', () => {
        const second = open(new Window({y: 10}));
        assert.equal(pendingIdle(), 1);
        extension.disable();
        assert.equal(pendingIdle(), 0);
        assert.equal(classes(), '');
        for (const object of [second, global.window_group, global.workspace_manager, Main.layoutManager, Main.panel])
            assert.equal(object.handlerCount, 0);
        second.emit('notify::allocation');
        assert.equal(pendingIdle(), 0);

        extension.enable();   // picks the existing window up again
        assert.equal(floating(), false);
        extension.disable();
        assert.equal(classes(), '');
    });

    await t.test('copes with no monitor at all', () => {
        Main.layoutManager.primaryMonitor = null;
        extension.enable(); assert.equal(floating(), true); extension.disable();
    });
});

// The two states differ in where the bar is (the margins of the theme's
// '#panel.floating-panel' rule) and in what GNOME Shell paints there. The Shell
// cross-fades the paint by itself; the bar has to be slid by hand.
test('sliding between the two states', async t => {
    const panel = Main.panel;
    Main.layoutManager.primaryMonitor = {index: 0, x: 0, y: 0, width: 1920, height: 1080};
    workspace.windows = []; global.actors = [];
    const window = new Window({y: 300});
    const extension = new FloatingPanel();
    extension.enable();
    const actor = open(window);
    settle();

    await t.test('takes the state it finds when it enables, without sliding', () => {
        assert.equal(floating(), true);
        assert.equal(panel.eased, null);
        assert.deepEqual(margins(), [GAP, GAP, GAP]);
        assert.equal(panel.translation_y, 0);
    });

    await t.test('slides the bar from where it was, for as long as the cross-fade', () => {
        window.y = PANEL; moved(actor);
        assert.equal(floating(), false);
        // The gap above the bar is part of the work area, so it goes at once
        // and the bar is held where it was by a translation instead.
        assert.equal(panel.margin_top, 0);
        assert.equal(panel.translation_y, GAP);
        assert.deepEqual(panel.eased.from, {translation_y: GAP, margin_left: GAP, margin_right: GAP});
        assert.deepEqual(panel.eased.targets, {translation_y: 0, margin_left: 0, margin_right: 0});
        assert.equal(panel.eased.duration, state.transition);
        assert.equal(panel.eased.mode, 'ease-out-quad');

        panel.finishEase();
        assert.deepEqual(margins(), [0, 0, 0]);
        assert.equal(panel.translation_y, 0);
    });

    await t.test('slides back out when the window leaves', () => {
        window.y = 300; moved(actor);
        assert.equal(floating(), true);
        assert.equal(panel.margin_top, GAP);
        assert.equal(panel.translation_y, -GAP);
        assert.deepEqual(panel.eased.targets, {translation_y: 0, margin_left: GAP, margin_right: GAP});
        panel.finishEase();
    });

    await t.test('carries on from where the bar is when the state changes mid-slide', () => {
        window.y = PANEL; moved(actor);
        panel.translation_y = 2; panel.margin_left = panel.margin_right = 2;   // part of the way up
        window.y = 300; moved(actor);
        assert.equal(floating(), true);
        assert.equal(panel.translation_y, 2 - GAP);
        assert.deepEqual(panel.eased.from, {translation_y: 2 - GAP, margin_left: 2, margin_right: 2});
        assert.deepEqual(panel.eased.targets, {translation_y: 0, margin_left: GAP, margin_right: GAP});
        panel.finishEase();
    });

    await t.test('does not start over while the state stays the same', () => {
        for (let i = 0; i < 3; i++) {
            moved(actor);
            assert.equal(panel.eased, null);
        }
        assert.equal(floating(), true);
    });

    await t.test('changes in one step with a theme that gives the panel no transition', () => {
        state.transition = 0;
        window.y = PANEL; moved(actor);
        assert.equal(floating(), false);
        assert.equal(panel.eased, null);
        assert.deepEqual(margins(), [0, 0, 0]);
        assert.equal(panel.translation_y, 0);
        state.transition = 250;
    });

    await t.test('changes in one step while the panel is off screen', () => {
        panel.mapped = false;
        window.y = 300; moved(actor);
        assert.equal(floating(), true);
        assert.equal(panel.eased, null);
        assert.deepEqual(margins(), [GAP, GAP, GAP]);
        assert.equal(panel.translation_y, 0);
        panel.mapped = true;
    });

    await t.test('leaves no half-finished slide behind on disable', () => {
        window.y = PANEL; moved(actor);
        assert.equal(panel.transitions.size, 3);

        extension.disable();
        assert.equal(panel.transitions.size, 0);
        assert.equal(panel.eased, null);
        assert.equal(panel.translation_y, 0);
        assert.deepEqual(margins(), [0, 0, 0]);
    });
});
