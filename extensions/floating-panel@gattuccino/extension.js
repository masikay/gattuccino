import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// The look of the two states comes from the Gattuccino shell theme
// (the floating-panel preference); this extension only decides which of the
// two classes the panel carries. With another theme it changes nothing.
const FLOATING_CLASS = 'floating-panel'; // no window is near
const DOCKED_CLASS = 'docked-panel';     // a window is maximized or close

// A window whose top edge is closer than this to the bottom of the panel docks
// it. Must stay larger than the gap the theme puts above the floating panel
// (the panel-gap preference, at most 12): a maximized or tiled window sits right
// below that gap and has to count as close in both states, otherwise the panel
// would flip back and forth.
const PROXIMITY = 16;

const WINDOW_TYPES = [
    Meta.WindowType.NORMAL,
    Meta.WindowType.DIALOG,
    Meta.WindowType.MODAL_DIALOG,
];

// Desktop icon extensions draw the desktop as a regular full-screen window
const IGNORED_APP_IDS = ['com.rastersoft.ding', 'com.desktop.ding'];

export default class FloatingPanelExtension extends Extension {
    enable() {
        this._signals = [];
        this._windowActors = new Map();
        this._idleId = 0;

        this._connect(global.window_group, 'child-added',
            (_group, actor) => this._trackWindowActor(actor));
        this._connect(global.window_group, 'child-removed',
            (_group, actor) => this._untrackWindowActor(actor));
        this._connect(global.workspace_manager, 'active-workspace-changed',
            () => this._queueUpdate());
        this._connect(Main.layoutManager, 'monitors-changed',
            () => this._queueUpdate());
        this._connect(Main.panel, 'notify::height',
            () => this._queueUpdate());

        for (const actor of global.get_window_actors())
            this._trackWindowActor(actor);

        this._update();
    }

    disable() {
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = null;

        for (const actor of [...this._windowActors.keys()])
            this._untrackWindowActor(actor);
        this._windowActors = null;

        // Last, as untracking the windows queues an update
        if (this._idleId) {
            GLib.source_remove(this._idleId);
            this._idleId = 0;
        }

        Main.panel.remove_style_class_name(FLOATING_CLASS);
        Main.panel.remove_style_class_name(DOCKED_CLASS);
    }

    _connect(object, signal, callback) {
        this._signals.push([object, object.connect(signal, callback)]);
    }

    _trackWindowActor(actor) {
        if (!(actor instanceof Meta.WindowActor) || this._windowActors.has(actor))
            return;

        this._windowActors.set(actor, [
            // moved, resized, maximized, tiled
            actor.connect('notify::allocation', () => this._queueUpdate()),
            // minimized, restored
            actor.connect('notify::visible', () => this._queueUpdate()),
            actor.connect('destroy', () => this._untrackWindowActor(actor, true)),
        ]);
        this._queueUpdate();
    }

    _untrackWindowActor(actor, destroyed = false) {
        const ids = this._windowActors?.get(actor);
        if (!ids)
            return;

        this._windowActors.delete(actor);
        if (!destroyed)
            ids.forEach(id => actor.disconnect(id));
        this._queueUpdate();
    }

    // Window geometry changes arrive in the middle of a layout pass, and
    // restyling the panel triggers another one: do it once things have settled.
    _queueUpdate() {
        if (this._idleId)
            return;

        this._idleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._idleId = 0;
            this._update();
            return GLib.SOURCE_REMOVE;
        });
    }

    _update() {
        const docked = this._hasWindowNearPanel();
        const [add, remove] = docked
            ? [DOCKED_CLASS, FLOATING_CLASS]
            : [FLOATING_CLASS, DOCKED_CLASS];

        Main.panel.remove_style_class_name(remove);
        Main.panel.add_style_class_name(add);
    }

    _hasWindowNearPanel() {
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor)
            return false;

        // The panel's own height is the same floating or docked (the gap is a
        // margin outside of it), so this limit does not move when the panel
        // changes state.
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const limit = monitor.y + Main.panel.height + PROXIMITY * scale;

        const workspace = global.workspace_manager.get_active_workspace();
        return workspace.list_windows().some(window =>
            window.get_monitor() === monitor.index &&
            !window.minimized &&
            window.showing_on_its_workspace() &&
            WINDOW_TYPES.includes(window.get_window_type()) &&
            !IGNORED_APP_IDS.includes(window.get_gtk_application_id()) &&
            // Maximized, tiled and fullscreen windows all start at the top of
            // the work area, so their position alone tells them apart.
            window.get_frame_rect().y < limit);
    }
}
