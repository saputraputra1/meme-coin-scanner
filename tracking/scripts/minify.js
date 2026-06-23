const { minify } = require('terser');
const fs = require('fs');
const path = require('path');

const PUBLIC = path.join(__dirname, '..', 'public');
const FILES = [
    { name: 'config.js', mangle: false, compress: true },
    { name: 'tracker.js', mangle: { toplevel: true }, compress: { passes: 2, drop_console: false, drop_debugger: true } },
    { name: 'firebase-config.js', mangle: { toplevel: true }, compress: { passes: 2 } },
];

async function main() {
    for (const file of FILES) {
        const fp = path.join(PUBLIC, file.name);
        if (!fs.existsSync(fp)) {
            console.log(`Skipping ${file.name} (not found)`);
            continue;
        }
        const code = fs.readFileSync(fp, 'utf8');
        const result = await minify(code, {
            compress: file.compress,
            mangle: file.mangle,
            output: { beautify: false, comments: false }
        });
        if (result.error) {
            console.error(`Error minifying ${file.name}:`, result.error);
            continue;
        }
        fs.writeFileSync(fp, result.code);
        const pct = Math.round((1 - result.code.length / code.length) * 100);
        console.log(`Minified ${file.name}: ${code.length} -> ${result.code.length} bytes (${pct}% reduction)`);
    }
    console.log('Done.');
}

main().catch(console.error);
