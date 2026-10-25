import assert from 'node:assert/strict';
import {test} from 'node:test';

import {loadExtension} from './load.mjs';
import {
    USER_THEME_DIR, environment, files, handlerCount, loadCalls, loaded, pendingIdle, pickAccent,
    pickStyle, replaceTheme, resetLoadCalls, settle,
    settings, switchTheme, written,
} from './catppuccin-accent.mocks.mjs';

const CatppuccinAccent = await loadExtension('catppuccin-accent@gattuccino', 'catppuccin-accent.mocks.mjs');
console.warn = () => {};

const theme = () => settings['org.gnome.shell.extensions.user-theme'].name;
const selectTheme = name => { settings['org.gnome.shell.extensions.user-theme'].name = name; };
const interfaceSettings = settings['org.gnome.desktop.interface'];
const stylesheet = (name, themes = '/home/u/.themes') => `${themes}/${name}/gnome-shell/gnome-shell.css`;
const dockSheet = (name, themes = '/home/u/.themes') => `${themes}/${name}/gnome-shell/gattuccino-dock.css`;

// The extension loads the dock stylesheet from an idle call, so that loading it
// does not re-enter the theme-changed handler that asked for it.
const dockLoaded = () => { settle(); return loaded(); };
const GTK4 = '/home/u/.config/gtk-4.0/gattuccino-accent.css';
const GTK3 = '/home/u/.config/gtk-3.0/gattuccino-accent.css';
const GTK4_CSS = '/home/u/.config/gtk-4.0/gtk.css';
const GTK3_CSS = '/home/u/.config/gtk-3.0/gtk.css';
const style = (dark = 'mocha') => `/* gattuccino: style (light=latte, dark=${dark})\n * anything */\n`;
const ours = (flavor, setting = 'follow') => `/* gattuccino: accent (flavor=${flavor}, accent=${setting})\n * anything */\n`;
const imports = flavor => `@import url("gattuccino-${flavor}.css");\n@import url("gattuccino-accent.css");\n`;

const VARIANTS = ['blue', 'teal', 'green', 'yellow', 'peach', 'red', 'pink', 'mauve', 'lavender'];
// [accent in Settings]: [Catppuccin accent, its Mocha color, its Latte color]
const SWATCHES = {
    blue: ['blue', '#89b4fa', '#1e66f5'], teal: ['teal', '#94e2d5', '#179299'],
    green: ['green', '#a6e3a1', '#40a02b'], yellow: ['yellow', '#f9e2af', '#df8e1d'],
    orange: ['peach', '#fab387', '#fe640b'], red: ['red', '#f38ba8', '#d20f39'],
    pink: ['pink', '#f5c2e7', '#ea76cb'], purple: ['mauve', '#cba6f7', '#8839ef'],
    slate: ['lavender', '#b4befe', '#7287fd'],
};

files.set(`${USER_THEME_DIR}/schemas/gschemas.compiled`, '');
for (const flavor of ['mocha', 'latte'])
    for (const accent of VARIANTS) files.set(stylesheet(`gattuccino-${flavor}-${accent}`), '');
files.set(GTK4_CSS, style());
files.set(GTK3_CSS, style());
files.set(GTK4, ours('mocha'));
files.set(GTK3, ours('mocha'));

test('catppuccin accent', async t => {
    const extension = new CatppuccinAccent();

    await t.test('applies the style and accent already picked when it is enabled', () => {
        interfaceSettings['accent-color'] = 'teal';
        selectTheme('gattuccino-mocha-blue');
        extension.enable();
        assert.equal(theme(), 'gattuccino-mocha-teal');
        assert.match(files.get(GTK4_CSS), /^\/\* gattuccino: style \(light=latte, dark=mocha\)\n/);
        assert.ok(files.get(GTK4_CSS).endsWith(imports('mocha')));
        assert.match(files.get(GTK4), /^\/\* gattuccino: accent \(flavor=mocha, accent=follow\)\n/);
        assert.match(files.get(GTK4), /--accent-bg-color: #94e2d5;\n  --accent-fg-color: #1e1e2e;\n  --accent-color: #94e2d5;\n/);
        assert.match(files.get(GTK4), /@define-color accent_bg_color #94e2d5;\n@define-color accent_fg_color #1e1e2e;\n@define-color accent_color #94e2d5;\n$/);
        assert.doesNotMatch(files.get(GTK3), /:root|--accent/);
        assert.match(files.get(GTK3), /@define-color accent_bg_color #94e2d5;/);
        assert.deepEqual(written.splice(0), [GTK4_CSS, GTK4, GTK3_CSS, GTK3]);
    });

    await t.test('maps every swatch of the picker, in the flavor of the style', () => {
        for (const [scheme, flavor, column] of [['prefer-dark', 'mocha', 1], ['default', 'latte', 2]]) {
            pickStyle(scheme);
            for (const [picked, colors] of Object.entries(SWATCHES)) {
                pickAccent(picked);
                assert.equal(theme(), `gattuccino-${flavor}-${colors[0]}`);
                assert.ok(files.get(GTK4).includes(`--accent-bg-color: ${colors[column]};`), picked);
                assert.ok(files.get(GTK3).includes(`accent_bg_color ${colors[column]};`), picked);
                assert.match(files.get(GTK3), new RegExp(`^/\\* gattuccino: accent \\(flavor=${flavor}, accent=follow\\)\\n`));
            }
        }
        assert.ok(files.get(GTK3).includes('accent_fg_color #eff1f5;'));
        written.length = 0;
        pickAccent('slate');   // unchanged: nothing is rewritten
        assert.deepEqual(written, []);
        pickStyle('prefer-dark');
    });

    await t.test('follows the style picked in Settings', () => {
        selectTheme('gattuccino-mocha-mauve');
        pickAccent('purple');
        interfaceSettings['gtk-theme'] = 'adw-gtk3-dark';

        pickStyle('default');
        assert.equal(theme(), 'gattuccino-latte-mauve');
        assert.ok(files.get(GTK4_CSS).endsWith(imports('latte')));
        assert.ok(files.get(GTK3_CSS).endsWith(imports('latte')));
        assert.ok(files.get(GTK4).includes('--accent-bg-color: #8839ef;'));
        assert.equal(interfaceSettings['gtk-theme'], 'adw-gtk3');

        pickStyle('prefer-light');
        assert.equal(theme(), 'gattuccino-latte-mauve');

        pickStyle('prefer-dark');
        assert.equal(theme(), 'gattuccino-mocha-mauve');
        assert.ok(files.get(GTK4_CSS).endsWith(imports('mocha')));
        assert.ok(files.get(GTK4).includes('--accent-bg-color: #cba6f7;'));
        assert.equal(interfaceSettings['gtk-theme'], 'adw-gtk3-dark');

        interfaceSettings['gtk-theme'] = 'Adwaita';   // not adw-gtk3: left alone
        pickStyle('default');
        assert.equal(interfaceSettings['gtk-theme'], 'Adwaita');
        pickStyle('prefer-dark');
    });

    await t.test('goes back to whichever dark flavor is installed, and keeps a fixed accent', () => {
        for (const flavor of ['latte', 'macchiato']) files.set(stylesheet(`mine-${flavor}-sky`), '');
        selectTheme('mine-latte-sky');
        pickStyle('default');
        pickStyle('prefer-dark');
        assert.equal(theme(), 'mine-macchiato-sky');
        pickAccent('purple');   // no mine-macchiato-mauve
        assert.equal(theme(), 'mine-macchiato-sky');
        pickStyle('default');
        assert.equal(theme(), 'mine-latte-sky');
        pickStyle('prefer-dark');
    });

    await t.test('keeps the fixed accent of the application colors', () => {
        files.set(GTK3_CSS, style('frappe'));   // the two folders need not agree
        files.set(GTK4, ours('mocha', 'sky'));
        files.set(GTK3, ours('frappe', 'sky'));
        pickAccent('red');
        assert.ok(files.get(GTK4).includes('--accent-bg-color: #89dceb;'));
        assert.ok(files.get(GTK3).includes('accent_bg_color #99d1db;'));
        assert.ok(files.get(GTK3_CSS).endsWith(imports('frappe')));
        pickStyle('default');
        assert.match(files.get(GTK4), /^\/\* gattuccino: accent \(flavor=latte, accent=sky\)\n/);
        assert.ok(files.get(GTK4).includes('--accent-bg-color: #04a5e5;'));
        assert.ok(files.get(GTK3_CSS).endsWith(imports('latte')));
        pickStyle('prefer-dark');
        assert.ok(files.get(GTK3).includes('accent_bg_color #99d1db;'));
        files.set(GTK3_CSS, style());
        files.set(GTK4, ours('mocha'));
        files.set(GTK3, ours('mocha'));
    });

    await t.test('leaves alone a shell theme that is not one of the variants', () => {
        for (const name of ['Adwaita-custom', '', 'red']) {
            selectTheme(name);
            pickAccent('red'); pickAccent('pink');
            pickStyle('default'); pickStyle('prefer-dark');
            assert.equal(theme(), name);
        }
        assert.ok(files.get(GTK4).includes('#f5c2e7'));   // applications still follow
    });

    await t.test('does not select a variant that is not installed', () => {
        files.set(stylesheet('other-teal'), '');
        selectTheme('other-teal');
        pickAccent('green');
        assert.equal(theme(), 'other-teal');
    });

    await t.test('finds variants in the other theme folders', () => {
        files.set(stylesheet('other-green', '/home/u/.local/share/themes'), '');
        pickAccent('blue'); pickAccent('green');
        assert.equal(theme(), 'other-green');
        files.set(stylesheet('other-red', '/usr/share/themes'), '');
        pickAccent('red');
        assert.equal(theme(), 'other-red');
    });

    await t.test('ignores an accent it does not know', () => {
        written.length = 0;
        pickAccent('magenta');
        assert.equal(theme(), 'other-red');
        assert.deepEqual(written, []);
    });

    await t.test('never creates the GTK files, and never rewrites ones that are not ours', () => {
        files.delete(GTK3);
        files.set(GTK4, '/* my own accent */\n');
        written.length = 0;
        pickAccent('teal');
        pickStyle('default'); pickStyle('prefer-dark');
        assert.deepEqual(written.filter(path => !path.endsWith('/gtk.css')), []);   // gtk.css is ours
        assert.equal(files.has(GTK3), false);
        assert.equal(files.get(GTK4), '/* my own accent */\n');

        files.set(GTK4, ours('mocha'));
        for (const css of ['YOURS', style('espresso')]) {   // not ours, or a flavor that does not exist
            files.set(GTK4_CSS, css);
            written.length = 0;
            pickAccent('blue'); pickStyle('default'); pickStyle('prefer-dark');
            assert.equal(written.filter(path => path.includes('gtk-4.0')).length, 0, css);
            assert.equal(files.get(GTK4_CSS), css);
        }
        files.set(GTK4_CSS, style());
        files.set(GTK3, ours('mocha'));
    });

    await t.test('still switches the shell theme when a file cannot be written', () => {
        selectTheme('gattuccino-mocha-teal');
        environment.failWrites = true;
        pickAccent('yellow');
        environment.failWrites = false;
        assert.equal(theme(), 'gattuccino-mocha-yellow');
    });

    await t.test('loads the accent rules for the dock that come with the theme', () => {
        for (const flavor of ['mocha', 'latte'])
            for (const accent of VARIANTS) files.set(dockSheet(`gattuccino-${flavor}-${accent}`), '');

        switchTheme('gattuccino-mocha-teal');
        assert.deepEqual(dockLoaded(), [dockSheet('gattuccino-mocha-teal')]);

        // the accent and the style select another variant: its own stylesheet
        pickAccent('purple');
        assert.deepEqual(dockLoaded(), [dockSheet('gattuccino-mocha-mauve')]);
        pickStyle('default');
        assert.deepEqual(dockLoaded(), [dockSheet('gattuccino-latte-mauve')]);
        pickStyle('prefer-dark');

        // a theme that is not ours, and one of ours built without the rules
        switchTheme('other-red');
        assert.deepEqual(dockLoaded(), []);
        files.delete(dockSheet('gattuccino-mocha-mauve'));
        switchTheme('gattuccino-mocha-mauve');
        assert.deepEqual(dockLoaded(), []);
        files.set(dockSheet('gattuccino-mocha-mauve'), '');

        // the stylesheets of a theme are dropped when GNOME Shell replaces it
        switchTheme('gattuccino-mocha-teal');
        replaceTheme();
        assert.deepEqual(dockLoaded(), [dockSheet('gattuccino-mocha-teal')]);

        // one that cannot be parsed leaves the rest of the extension working
        environment.failLoads = true;
        switchTheme('gattuccino-mocha-sky');
        assert.deepEqual(dockLoaded(), []);
        environment.failLoads = false;
        pickAccent('teal');
        assert.equal(theme(), 'gattuccino-mocha-teal');
        assert.deepEqual(dockLoaded(), [dockSheet('gattuccino-mocha-teal')]);

        // and one found in another theme folder
        files.set(dockSheet('gattuccino-mocha-sky', '/usr/share/themes'), '');
        switchTheme('gattuccino-mocha-sky');
        assert.deepEqual(dockLoaded(), [dockSheet('gattuccino-mocha-sky', '/usr/share/themes')]);
    });

    await t.test('loading the dock stylesheet does not send it round again', () => {
        // Loading a stylesheet makes St say the theme changed, which is the
        // signal that asks for the stylesheet: doing it inline recursed until
        // the JS stack ran out, which is what unlocking the screen used to hit.
        for (const accent of VARIANTS) files.set(dockSheet(`gattuccino-mocha-${accent}`), '');
        switchTheme('gattuccino-mocha-teal');
        settle();

        resetLoadCalls();
        replaceTheme();   // a new theme to fill, as a theme reload gives
        assert.equal(pendingIdle(), 1, 'queued, not loaded inline');
        settle();         // throws rather than hangs if it will not settle
        assert.equal(loadCalls(), 1, 'loaded once, however often the theme says it changed');
        assert.deepEqual(loaded(), [dockSheet('gattuccino-mocha-teal')]);
        assert.equal(pendingIdle(), 0);

        // a burst of theme changes, as unlocking sets off, collapses into one
        resetLoadCalls();
        for (let i = 0; i < 5; i++)
            replaceTheme();
        assert.equal(pendingIdle(), 1);
        settle();
        assert.equal(loadCalls(), 1);
        assert.deepEqual(loaded(), [dockSheet('gattuccino-mocha-teal')]);
    });

    await t.test('disconnects on disable and reverts nothing', () => {
        pickAccent('yellow');
        const before = [theme(), files.get(GTK4)];
        extension.disable();
        assert.equal(handlerCount(), 0);
        assert.deepEqual(dockLoaded(), []);   // except the stylesheet, which is loaded into the theme
        assert.deepEqual([theme(), files.get(GTK4)], before);
        pickAccent('blue');
        pickStyle('default');
        assert.equal(theme(), 'gattuccino-mocha-yellow');
        extension.enable();
        assert.equal(theme(), 'gattuccino-latte-blue');
        assert.deepEqual(dockLoaded(), [dockSheet('gattuccino-latte-blue')]);
        extension.disable();
        pickStyle('prefer-dark');
    });

    await t.test('works with User Themes packaged by the distribution', () => {
        environment.userThemes = 'system';
        pickAccent('teal');
        extension.enable();
        assert.equal(theme(), 'gattuccino-mocha-teal');
        extension.disable();
    });

    await t.test('still recolors applications without User Themes', () => {
        environment.userThemes = false;
        extension.enable();
        pickAccent('red');
        assert.equal(theme(), 'gattuccino-mocha-teal');
        assert.ok(files.get(GTK4).includes('#f38ba8'));
        assert.deepEqual(dockLoaded(), []);   // which theme is selected is not known either
        extension.disable();

        environment.userThemes = 'user';   // installed, but its schemas are not compiled
        files.delete(`${USER_THEME_DIR}/schemas/gschemas.compiled`);
        files.set(`${USER_THEME_DIR}/schemas/schema.xml`, '');
        extension.enable();
        pickAccent('pink');
        assert.ok(files.get(GTK4).includes('#f5c2e7'));
        extension.disable();
        assert.equal(handlerCount(), 0);
    });
});
