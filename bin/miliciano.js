#!/usr/bin/env node
const { spawnSync } = require('child_process');
const path = require('path');

const pythonCandidates = [process.env.MILICIANO_PYTHON, 'python3', 'python'].filter(Boolean);
const script = path.join(__dirname, '..', 'miliciano-poc', 'bin', 'miliciano');
const vendorPython = path.join(__dirname, '..', 'vendor', 'python');
const args = [script, ...process.argv.slice(2)];
const pathSeparator = process.platform === 'win32' ? ';' : ':';

function buildPythonPath() {
  const current = process.env.PYTHONPATH || '';
  return current ? `${vendorPython}${pathSeparator}${current}` : vendorPython;
}

let lastError = null;
for (const python of pythonCandidates) {
  const res = spawnSync(python, args, {
    stdio: 'inherit',
    env: {
      ...process.env,
      PYTHONPATH: buildPythonPath(),
    },
  });
  if (!res.error) {
    process.exit(typeof res.status === 'number' ? res.status : 0);
  }
  lastError = res.error;
}

console.error('[Miliciano] no pude encontrar python3/python para arrancar el CLI.');
if (lastError) {
  console.error(lastError.message || String(lastError));
}
process.exit(1);
