const JavaScriptObfuscator = require('javascript-obfuscator');
const { minify } = require('terser');
const fs = require('fs');
const path = require('path');

const PUBLIC = path.join(__dirname, '..', 'public');
const OUT = 'app.js';
const BUNDLE = ['config.js', 'firebase-config.js', 'tracker.js', 'features.js'];
const RESERVED = ['auth', 'fdb', 'socket', 'requestPermissions'];

async function main() {
    // Step 1: Concatenate source files
    let combined = '';
    for (const file of BUNDLE) {
        const fp = path.join(PUBLIC, file);
        if (!fs.existsSync(fp)) { console.log(`Skipping ${file}`); continue; }
        combined += fs.readFileSync(fp, 'utf8') + ';';
    }

    // Step 2: Minify with terser to resolve duplicate declarations and reduce size
    const minified = await minify(combined, {
        compress: { passes: 2, drop_console: false, drop_debugger: true },
        mangle: { toplevel: true, reserved: RESERVED },
        output: { beautify: false, comments: false }
    });

    if (minified.error) {
        console.error('Terser error:', minified.error);
        process.exit(1);
    }

    // Step 3: Obfuscate the minified bundle
    const obfuscated = JavaScriptObfuscator.obfuscate(minified.code, {
        compact: true,
        controlFlowFlattening: false,
        deadCodeInjection: false,
        debugProtection: false,
        disableConsoleOutput: false,
        identifierNamesGenerator: 'mangled',
        renameGlobals: false,
        selfDefending: false,
        stringArray: true,
        stringArrayEncoding: ['base64'],
        stringArrayThreshold: 0.8,
        reservedNames: RESERVED.map(n => '^' + n + '$')
    });

    const output = obfuscated.getObfuscatedCode();
    fs.writeFileSync(path.join(PUBLIC, OUT), output);

    const pct = Math.round((1 - output.length / combined.length) * 100);
    console.log(`Obfuscated: ${combined.length} -> ${output.length} bytes (${pct}% reduction)`);
    console.log('Done.');
}

main().catch(console.error);
