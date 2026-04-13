#!/usr/bin/env node
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..');
const requiredRoots = [
  'README.md',
  'CHANGELOG.md',
  'bin/miliciano.js',
  'miliciano-poc/bin',
  'miliciano-poc/config',
];
const ignoredSegments = new Set(['__pycache__']);

function shouldIgnore(relativePath) {
  const normalized = relativePath.replaceAll(path.sep, '/');
  return normalized.endsWith('.pyc') || normalized.split('/').some((segment) => ignoredSegments.has(segment));
}

function walk(relativePath) {
  const absolutePath = path.join(repoRoot, relativePath);
  const stat = fs.statSync(absolutePath);
  if (stat.isFile()) {
    return shouldIgnore(relativePath) ? [] : [relativePath.replaceAll(path.sep, '/')];
  }
  return fs.readdirSync(absolutePath, { withFileTypes: true }).flatMap((entry) => {
    const childRelative = path.join(relativePath, entry.name);
    if (shouldIgnore(childRelative)) {
      return [];
    }
    if (entry.isDirectory()) {
      return walk(childRelative);
    }
    return [childRelative.replaceAll(path.sep, '/')];
  });
}

function expectedFiles() {
  return new Set(requiredRoots.flatMap((relativePath) => walk(relativePath)));
}

function packedFiles() {
  const stdout = execFileSync(
    'npm',
    ['pack', '--dry-run', '--json', '--ignore-scripts'],
    { cwd: repoRoot, encoding: 'utf8' },
  );
  const parsed = JSON.parse(stdout);
  const files = parsed[0] && parsed[0].files ? parsed[0].files : [];
  return new Set(files.map((entry) => entry.path));
}

const expected = expectedFiles();
const packed = packedFiles();
const missing = [...expected].filter((file) => !packed.has(file)).sort();
const forbidden = [...packed].filter((file) => shouldIgnore(file)).sort();

if (missing.length > 0) {
  console.error('Package verification failed. Missing tarball files:');
  for (const file of missing) {
    console.error(`- ${file}`);
  }
  process.exit(1);
}

if (forbidden.length > 0) {
  console.error('Package verification failed. Forbidden generated files present:');
  for (const file of forbidden) {
    console.error(`- ${file}`);
  }
  process.exit(1);
}

console.log(`Package verification OK (${expected.size} required files present).`);
