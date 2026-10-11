// Loads an extension outside GNOME Shell: its imports of GNOME modules are
// pointed at a file of stand-ins, and the result is imported from a temporary
// copy.
import {mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

export const extensionPath = uuid => resolve(here, '../../extensions', uuid, 'extension.js');

export async function loadExtension(uuid, mocksFile) {
    const mocks = pathToFileURL(resolve(here, mocksFile)).href;
    const names = [];
    const source = readFileSync(extensionPath(uuid), 'utf8')
        .replace(/^import (?:\* as )?(\w+|\{\w+\}) from '(?:gi|resource):\/\/[^']+';\n/gm, (_, name) => {
            names.push(name.replace(/[{}]/g, ''));
            return '';
        });
    const copy = join(mkdtempSync(join(tmpdir(), 'gattuccino-test-')), 'extension.mjs');
    writeFileSync(copy, `import {${names.join(', ')}} from '${mocks}';\n${source}`);
    return (await import(pathToFileURL(copy).href)).default;
}
