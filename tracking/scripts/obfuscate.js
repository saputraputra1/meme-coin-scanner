const JavaScriptObfuscator = require('javascript-obfuscator');
const fs = require('fs');
const path = require('path');

const PUBLIC = path.join(__dirname, '..', 'public');
const OUT = 'app.js';
const BUNDLE = ['config.js', 'firebase-config.js', 'tracker.js'];
const RESERVED = ['auth', 'fdb', 'socket', 'requestPermissions'];

let combined = '';
for (const file of BUNDLE) {
    const fp = path.join(PUBLIC, file);
    if (!fs.existsSync(fp)) { console.log(`Skipping ${file}`); continue; }
    combined += fs.readFileSync(fp, 'utf8') + ';';
}

const obfuscated = JavaScriptObfuscator.obfuscate(combined, {
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
