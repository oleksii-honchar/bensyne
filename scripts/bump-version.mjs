#!/usr/bin/env node
/**
 * Shared semantic version bumper for monorepo apps.
 *
 * Scans commit subjects after the last commit that touched the app's
 * version file and bumps the current version per Conventional Commits:
 *   - "BREAKING CHANGE" anywhere in subject, or a `!` before `:` in
 *     type-scope (e.g. `feat!:` / `feat(api)!:`)  -> major
 *   - `feat`                                       -> minor
 *   - anything else                                -> patch
 *   - no commits since last version touch          -> no-op (exit 0)
 *
 * The version is written in place into the first
 *   version = "x.y.z"
 * line of the version file (pyproject.toml for Python apps).
 *
 * CLI:
 *   node scripts/bump-version.mjs --app <appRoot> [--version-file <file>] [--dry-run]
 *
 *   --app          App root, relative to repo root (e.g. apps/bensyne-mcp)
 *                  Required. The version file must live under this app.
 *   --version-file Version file path, relative to repo root.
 *                  Default: <app>/pyproject.toml
 *   --dry-run      Report old->new + scanned commit list; write nothing.
 *
 * Exit codes: 0 = ok (incl. no-op), 1 = usage / git / parse error.
 */

import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

function git(args) {
  return execFileSync('git', args, { encoding: 'utf8' }).trim();
}

function fail(message) {
  console.error(`bump-version: ${message}`);
  process.exit(1);
}

// --- parse CLI -------------------------------------------------------------
const argv = process.argv.slice(2);
let appRoot = null;
let versionFile = null;
let dryRun = false;

for (let i = 0; i < argv.length; i++) {
  const arg = argv[i];
  if (arg === '--app') {
    appRoot = argv[++i];
  } else if (arg === '--version-file') {
    versionFile = argv[++i];
  } else if (arg === '--dry-run') {
    dryRun = true;
  } else {
    fail(`unknown argument: ${arg}\nUsage: node scripts/bump-version.mjs --app <appRoot> [--version-file <file>] [--dry-run]`);
  }
}

if (!appRoot) {
  fail('missing required --app <appRoot>\nUsage: node scripts/bump-version.mjs --app <appRoot> [--version-file <file>] [--dry-run]');
}
if (!versionFile) {
  versionFile = path.posix.join(appRoot, 'pyproject.toml');
}

// repo root = two levels up from this script (scripts/bump-version.mjs)
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
process.chdir(repoRoot);

// --- read current version --------------------------------------------------
let content;
try {
  content = readFileSync(versionFile, 'utf8');
} catch {
  fail(`version file not found: ${versionFile}`);
}
const match = content.match(/^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"/m);
if (!match) {
  fail(`no version = "x.y.z" line in ${versionFile}`);
}
const current = [Number(match[1]), Number(match[2]), Number(match[3])];

// --- find commits since last version touch ----------------------------------
let lastVersionCommit;
try {
  lastVersionCommit = git(['log', '-1', '--format=%H', '--', versionFile]);
} catch (err) {
  fail(`git log failed: ${err.message}`);
}

const range = lastVersionCommit ? `${lastVersionCommit}..HEAD` : 'HEAD';
let subjects;
try {
  subjects = git(['log', '--format=%s', range]).split('\n').filter(Boolean);
} catch (err) {
  fail(`git log failed: ${err.message}`);
}

// --- classify ---------------------------------------------------------------
const BREAKING_RE = /BREAKING CHANGE/;
const CONV_RE = /^(\w+)(\([^)]*\))?(!)?:/;

function bumpFor(subjects) {
  let level = 'patch';
  for (const subject of subjects) {
    if (BREAKING_RE.test(subject)) return 'major';
    const m = subject.match(CONV_RE);
    if (m && m[3] === '!') return 'major';
    if (m && m[1] === 'feat' && level !== 'minor') level = 'minor';
  }
  return level;
}

if (subjects.length === 0) {
  console.log(`bump-version: no commits since ${lastVersionCommit ? lastVersionCommit.slice(0, 7) : '(start)'} — version stays ${current.join('.')}`);
  process.exit(0);
}

const level = bumpFor(subjects);
const next = [...current];
if (level === 'major') {
  next[0] += 1;
  next[1] = 0;
  next[2] = 0;
} else if (level === 'minor') {
  next[1] += 1;
  next[2] = 0;
} else {
  next[2] += 1;
}

const oldVersion = current.join('.');
const newVersion = next.join('.');

console.log(`bump-version: ${oldVersion} -> ${newVersion} (${level})`);
console.log(`Scanned ${subjects.length} commit(s) since ${lastVersionCommit ? lastVersionCommit.slice(0, 7) : '(start)'}:`);
for (const subject of subjects) {
  console.log(`  - ${subject}`);
}

if (dryRun) {
  console.log('dry-run: no file written');
  process.exit(0);
}

writeFileSync(versionFile, content.replace(match[0], `version = "${newVersion}"`));
console.log(`wrote version = "${newVersion}" to ${versionFile}`);
