import assert from 'node:assert/strict';
import {test} from 'node:test';

import {loadExtension} from './load.mjs';
import {ExtensionPreferences, Settings, Window, row} from './prefs.mocks.mjs';

async function prefs(uuid, values) {
    const Preferences = await loadExtension(uuid, 'prefs.mocks.mjs', 'prefs.js');
    ExtensionPreferences.settings = new Settings(values);
    const window = new Window();
    new Preferences().fillPreferencesWindow(window);
    return {settings: ExtensionPreferences.settings, window};
}

test('the blur preferences', async t => {
    const {settings, window} = await prefs('blur@gattuccino', {radius: 32, background: true, 'background-radius': 20});

    await t.test('show the settings as they are', () => {
        assert.equal(row(window, 'Blur radius').value, 32);
        assert.equal(row(window, 'Blur the wallpaper').active, true);
        assert.equal(row(window, 'Wallpaper blur radius').value, 20);
    });

    await t.test('change a setting as a row is changed, and the other way round', () => {
        row(window, 'Blur radius').value = 12;
        assert.equal(settings.get_int('radius'), 12);
        settings._set('radius', 40);           // changed somewhere else, say by `gattuccino configure`
        assert.equal(row(window, 'Blur radius').value, 40);
    });

    await t.test('leave the radius of the wallpaper alone while it is not blurred', () => {
        row(window, 'Blur the wallpaper').active = false;
        assert.equal(settings.get_boolean('background'), false);
        assert.equal(row(window, 'Wallpaper blur radius').sensitive, false);
        row(window, 'Blur the wallpaper').active = true;
        assert.equal(row(window, 'Wallpaper blur radius').sensitive, true);
    });
});

test('the floating bar preferences', async t => {
    const {settings, window} = await prefs('floating-panel@gattuccino', {gap: 6, radius: 'round'});

    await t.test('show a round bar as a switch, and the radius out of reach', () => {
        assert.equal(row(window, 'Gap').value, 6);
        assert.equal(row(window, 'Fully round').active, true);
        assert.equal(row(window, 'Corner radius').sensitive, false);
    });

    await t.test('take a radius in pixels when it is not round', () => {
        row(window, 'Fully round').active = false;
        assert.equal(row(window, 'Corner radius').sensitive, true);
        row(window, 'Corner radius').value = 14;
        assert.equal(settings.get_string('radius'), '14');
        row(window, 'Gap').value = 10;
        assert.equal(settings.get_int('gap'), 10);
    });

    await t.test('follow a setting changed elsewhere, without writing it back', () => {
        settings._set('radius', 'round');
        assert.equal(row(window, 'Fully round').active, true);
        settings._set('radius', '8');
        assert.equal(row(window, 'Fully round').active, false);
        assert.equal(row(window, 'Corner radius').value, 8);
        assert.equal(settings.get_string('radius'), '8');
    });
});

test('the dock preferences', async t => {
    const {settings, window} = await prefs('catppuccin-accent@gattuccino', {'dock-radius': 'dock', 'show-apps-icon': ''});

    await t.test('show Dash to Dock\'s own corners, with no radius to give', () => {
        assert.equal(row(window, 'Corners').selected, 0);
        assert.equal(row(window, 'Corner radius').visible, false);
    });

    await t.test('write the corners as they are chosen', () => {
        row(window, 'Corners').selected = 1;
        assert.equal(settings.get_string('dock-radius'), 'round');
        row(window, 'Corners').selected = 2;
        assert.equal(row(window, 'Corner radius').visible, true);
        row(window, 'Corner radius').value = 18;
        assert.equal(settings.get_string('dock-radius'), '18');
        row(window, 'Corners').selected = 0;
        assert.equal(settings.get_string('dock-radius'), 'dock');
    });

    await t.test('follow a setting changed elsewhere', () => {
        settings._set('dock-radius', '24');
        assert.equal(row(window, 'Corners').selected, 2);
        assert.equal(row(window, 'Corner radius').value, 24);
    });

    await t.test('write the icon when it is applied, and show one that was set elsewhere', () => {
        const icon = row(window, 'Show Applications icon');
        icon.text = ' /home/u/apps-{flavor}.svg ';
        icon.emit('apply');
        assert.equal(settings.get_string('show-apps-icon'), '/home/u/apps-{flavor}.svg');
        settings._set('show-apps-icon', '/home/u/other.svg');
        assert.equal(icon.text, '/home/u/other.svg');
    });
});
