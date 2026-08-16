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
 * The version is written in place into the version file:
 *   - pyproject.toml  -> first `version = "x.y.z"` line (Python apps)
 *   - package.json    -> top-level `"version": "x.y.z"` field, preserving
 *     formatting; if a sibling package-lock.json exists its root "version"
 *     and packages[""].version fields are synced too.
 *
 * CLI:
 *   node scripts/bump-version.mjs --app <appRoot> [--version-file <file>] [--dry-run]
 *
 *   --app          App root, relative to repo root (e.g. apps/bensyne-mcp)
 *                  Required. The version file must live under this app.
 *   --version-file Version file path, relative to repo root.
 *                  Default: <app>/pyproject.toml if it exists, else
 *                  <app>/package.json
 *   --dry-run      Report old->new + scanned commit list; write nothing.
 *
 * Exit codes: 0 = ok (incl. no-op), 1 = usage / git / parse error.
 */

import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
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
// repo root = two levels up from this script (scripts/bump-version.mjs)
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
process.chdir(repoRoot);

if (!versionFile) {
  const pyproject = path.posix.join(appRoot, 'pyproject.toml');
  versionFile = existsSync(pyproject) ? pyproject : path.posix.join(appRoot, 'package.json');
}

// --- read current version --------------------------------------------------
let content;
try {
  content = readFileSync(versionFile, 'utf8');
} catch {
  fail(`version file not found: ${versionFile}`);
}
const isJson = versionFile.endsWith('.json');
let current;
if (isJson) {
  let parsed;
  try {
    parsed = JSON.parse(content);
  } catch (err) {
    fail(`invalid JSON in ${versionFile}: ${err.message}`);
  }
  const m = String(parsed.version ?? '').match(/^(\d+)\.(\d+)\.(\d+)$/);
  if (!m) fail(`no top-level "version": "x.y.z" in ${versionFile}`);
  current = [Number(m[1]), Number(m[2]), Number(m[3])];
} else {
  const match = content.match(/^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"/m);
  if (!match) fail(`no version = "x.y.z" line in ${versionFile}`);
  current = [Number(match[1]), Number(match[2]), Number(match[3])];
}

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

if (isJson) {
  // Rewrite only the top-level "version" field; preserve file formatting.
  const versionLineRe = /^(\s*)"version"\s*:\s*"[^"]*"(,?)$/m;
  if (!versionLineRe.test(content)) fail(`no top-level "version" line in ${versionFile}`);
  writeFileSync(versionFile, content.replace(versionLineRe, `$1"version": "${newVersion}"$2`));
  console.log(`wrote "version": "${newVersion}" to ${versionFile}`);

  // Sync package-lock.json (root version + packages[""].version) if present.
  const lockFile = path.posix.join(path.posix.dirname(versionFile), 'package-lock.json');
  if (existsSync(lockFile)) {
    const lockContent = readFileSync(lockFile, 'utf8');
    let lockParsed;
    try {
      lockParsed = JSON.parse(lockContent);
    } catch (err) {
      fail(`invalid JSON in ${lockFile}: ${err.message}`);
    }
    if (typeof lockParsed.version === 'string') lockParsed.version = newVersion;
    if (lockParsed.packages && typeof lockParsed.packages[''].version === 'string') {
      lockParsed.packages[''].version = newVersion;
    }
    writeFileSync(lockFile, JSON.stringify(lockParsed, null, 2) + '\n');
    console.log(`synced version "${newVersion}" in ${lockFile}`);
  }
} else {
  const match = content.match(/^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"/m);
  writeFileSync(versionFile, content.replace(match[0], `version = "${newVersion}"`));
  console.log(`wrote version = "${newVersion}" to ${versionFile}`);
}
