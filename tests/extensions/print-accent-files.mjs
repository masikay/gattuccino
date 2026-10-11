// Prints, as JSON, the files the catppuccin-accent extension writes for every
// flavor and every accent of the picker: the two accent files, and gtk.css in
// the style of the flavor. tests/test_extensions.py compares them with what
// the installer writes.
import {loadExtension} from './load.mjs';
import {files, pickAccent, settings} from './catppuccin-accent.mocks.mjs';

const CatppuccinAccent = await loadExtension('catppuccin-accent@gattuccino', 'catppuccin-accent.mocks.mjs');
const config = '/home/u/.config';
const paths = {'gtk-4.0': `${config}/gtk-4.0/gattuccino-accent.css`, 'gtk-3.0': `${config}/gtk-3.0/gattuccino-accent.css`};
const result = {};
const extension = new CatppuccinAccent();
extension.enable();
for (const flavor of ['latte', 'frappe', 'macchiato', 'mocha']) {
    const dark = flavor !== 'latte';
    settings['org.gnome.desktop.interface']['color-scheme'] = dark ? 'prefer-dark' : 'default';
    result[flavor] = {};
    for (const picked of ['blue', 'teal', 'green', 'yellow', 'orange', 'red', 'pink', 'purple', 'slate']) {
        for (const folder of Object.keys(paths))
            files.set(`${config}/${folder}/gtk.css`, `/* gattuccino: style (light=latte, dark=${dark ? flavor : 'mocha'})\n */\n`);
        for (const path of Object.values(paths))
            files.set(path, `/* gattuccino: accent (flavor=${flavor}, accent=follow)\n */\n`);
        pickAccent('unknown');
        pickAccent(picked);
        result[flavor][picked] = Object.fromEntries(Object.entries(paths).map(([folder, path]) => [folder, files.get(path)]));
        result[flavor][picked]['gtk.css'] = files.get(`${config}/gtk-4.0/gtk.css`);
    }
}
console.log(JSON.stringify(result));
