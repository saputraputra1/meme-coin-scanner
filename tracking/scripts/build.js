const { minify } = require('terser');
const fs = require('fs');
const path = require('path');

const PUBLIC = path.join(__dirname, '..', 'public');
const OUT = 'app.js';

// Bundle order: config (global vars), firebase-config (Firebase init), tracker (main logic)
const BUNDLE = ['config.js', 'firebase-config.js', 'tracker.js'];

async function main() {
    let combined = '';
    for (const file of BUNDLE) {
        const fp = path.join(PUBLIC, file);
        if (!fs.existsSync(fp)) {
            console.log(`Skipping ${file} (not found)`);
            continue;
        }
        combined += fs.readFileSync(fp, 'utf8') + ';';
    }
    
    const result = await minify(combined, {
        compress: { passes: 2, drop_console: false, drop_debugger: true },
        mangle: { toplevel: true, reserved: ['auth', 'fdb', 'socket', 'requestPermissions'] },
        output: { beautify: false, comments: false }
    });
    
    if (result.error) {
        console.error('Error:', result.error);
        process.exit(1);
    }
    
    // Write bundled output
    fs.writeFileSync(path.join(PUBLIC, OUT), result.code);
    
    const pct = Math.round((1 - result.code.length / combined.length) * 100);
    console.log(`Bundled ${BUNDLE.join(', ')} -> ${OUT}`);
    console.log(`Size: ${combined.length} -> ${result.code.length} bytes (${pct}% reduction)`);
    console.log('Done.');
}

main().catch(console.error);
