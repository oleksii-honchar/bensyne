#!/usr/bin/env node
/**
 * assert-baseline.mjs — Task 1: Baseline capture & preflight guard.
 *
 * Asserts the CURRENT `apps/racochu/package.json` matches the pre-bump baseline
 * captured in the session spec (`specifications/spec.md`, "Technology Stack
 * (bump-only)" table — CURRENT column) and in this file on 2026-08-30.
 *
 * Green (exit 0) on the untouched pre-bump repo — this script IS the recorded
 * baseline guard. It turns RED (exit 1, listing every failure) the moment any
 * of the 17 bump targets, 7 excluded majors, 4 overrides zod pins, engines, or
 * allowScripts drift from the baseline.
 *
 * Behavior assertions only (JSON field equality) — never logger calls.
 *
 * Run (from repo root or apps/racochu):
 *   node apps/racochu/scripts-dev/assert-baseline.mjs
 */
import { readFileSync } from 'node:fs';

const pkgPath = new URL('../package.json', import.meta.url);
const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));

/** Baseline expectations — pre-bump (CURRENT) values from the spec table. */
const baseline = {
  // --- 17 bump targets: dependencies (8) ---
  dependencies: {
    '@ai-sdk/openai': '4.0.36',
    config: '5.0.0',
    picomatch: '^4.0.4',
    '@dotenvx/dotenvx': '2.20.1',
    '@mastra/rag': '2.4.2',
    '@prisma/adapter-better-sqlite3': '^7.9.1',
    '@prisma/client': '^7.9.1',
    'js-yaml': '5.2.3',
    // zod is a bump target; pin checked below
  },
  // --- 17 bump targets: devDependencies (9) ---
  devDependencies: {
    '@faker-js/faker': '^10.5.0',
    '@types/node': '26.2.0',
    '@typescript-eslint/eslint-plugin': '^8.66.0',
    '@typescript-eslint/parser': '^8.66.0',
    eslint: '10.8.0',
    globals: '^17.9.0',
    jest: '^30.4.2',
    prisma: '^7.9.1',
    'typescript-eslint': '8.66.0',
    // exclude typescript here — it is a major exclusion, asserted below
  },
  // --- 7 excluded majors: UNCHANGED from the file's current values ---
  excludedMajors: {
    dependencies: {
      '@nestjs/common': '11.1.28',
      '@nestjs/config': '4.0.4',
      '@nestjs/core': '11.1.28',
      '@nestjs/event-emitter': '^3.1.0',
    },
    devDependencies: {
      '@nestjs/platform-express': '^11.1.28',
      '@nestjs/testing': '11.1.28',
      typescript: '^6.0.3',
    },
  },
  // --- direct zod pin (part of the 17; kept separate for the overrides check) ---
  'direct-zod': '4.4.3',
  overrides: {
    '@ai-sdk/openai': '4.4.3',
    '@ai-sdk/ui-utils-v5': '4.4.3',
    '@ai-sdk/provider-utils@2.2.8': '4.4.3',
    'zod-to-json-schema': '4.4.3',
  },
  engines: { node: '>=26.0.0', npm: '>=11.0.0' },
  allowScripts: {
    'protobufjs@7.6.5': true,
    'unrs-resolver@1.12.2': true,
  },
};

const failures = [];

function assertEqual(section, key, expected) {
  const got = section?.[key];
  if (got !== expected) {
    failures.push(`expected ${key} === "${expected}" but got ${JSON.stringify(got)}`);
  }
}

// 1. All 17 bump targets resolve to their pre-bump (Current) versions exactly.
for (const [key, expected] of Object.entries(baseline.dependencies)) {
  assertEqual(pkg.dependencies, key, expected);
}
for (const [key, expected] of Object.entries(baseline.devDependencies)) {
  assertEqual(pkg.devDependencies, key, expected);
}
assertEqual(pkg.dependencies, 'zod', baseline['direct-zod']);

// 2. All 7 excluded majors present and unchanged from the current file values.
for (const [key, expected] of Object.entries(baseline.excludedMajors.dependencies)) {
  assertEqual(pkg.dependencies, key, expected);
}
for (const [key, expected] of Object.entries(baseline.excludedMajors.devDependencies)) {
  assertEqual(pkg.devDependencies, key, expected);
}

// 3. All 4 overrides zod pins equal "4.4.3".
for (const [key, expected] of Object.entries(baseline.overrides)) {
  const pin = pkg.overrides?.[key]?.zod;
  if (pin !== expected) {
    failures.push(
      `expected overrides["${key}"].zod === "${expected}" but got ${JSON.stringify(pin)}`,
    );
  }
}

// 4. engines equals the baseline.
const enginesKey = JSON.stringify(baseline.engines, null, 2);
if (JSON.stringify(pkg.engines) !== JSON.stringify(baseline.engines)) {
  failures.push(`expected engines === ${enginesKey} but got ${JSON.stringify(pkg.engines, null, 2)}`);
}

// 5. allowScripts unchanged.
for (const [key, expected] of Object.entries(baseline.allowScripts)) {
  if (pkg.allowScripts?.[key] !== expected) {
    failures.push(
      `expected allowScripts["${key}"] === ${expected} but got ${JSON.stringify(pkg.allowScripts?.[key])}`,
    );
  }
}

if (failures.length > 0) {
  console.error('BASELINE DRIFT — the following assertions FAILED:');
  for (const failure of failures) {
    console.error(`  - ${failure}`);
  }
  process.exit(1);
}

console.error('assert-baseline: OK — package.json matches the pre-bump baseline');
process.exit(0);