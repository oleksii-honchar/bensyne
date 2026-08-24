import { describe, expect, it } from '@jest/globals';
import { readFileSync } from 'node:fs';

/**
 * Static config-wiring tests for the `start:resume` npm script + nx target.
 *
 * These assert CONFIG BEHAVIOR only — that the script command is exact
 * (kill-stale prepend + --resume flag) and that the nx target mirrors the
 * `start:reprocess` wiring so `nx run racochu:start:resume` no longer falls
 * back silently to plain `start`. Never asserts logger calls.
 *
 * Written RED-first: the nx target did not exist when this file was created,
 * so the project.json assertions failed before the target was added.
 *
 * Run with: npm test (chains `jest --config jest.scripts.config.cjs` for the
 * dependency-free ESM scripts suite).
 */
const pkgPath = new URL('../package.json', import.meta.url);
const projectPath = new URL('../project.json', import.meta.url);

const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
const project = JSON.parse(readFileSync(projectPath, 'utf8'));

describe('start:resume npm script', () => {
  it('exists with the exact expected command (kill-stale prepend + --resume)', () => {
    expect(pkg.scripts['start:resume']).toBe(
      'node scripts/kill-stale-racochu.mjs && node dist/src/main.js --resume',
    );
  });
});

describe('start:resume nx target', () => {
  it('exists (so nx run racochu:start:resume does not fall back to plain start)', () => {
    expect(project.targets['start:resume']).toBeDefined();
  });

  it('uses nx:run-commands with cwd apps/racochu', () => {
    expect(project.targets['start:resume'].executor).toBe('nx:run-commands');
    expect(project.targets['start:resume'].options.cwd).toBe('apps/racochu');
  });

  it('invokes the npm start:resume script', () => {
    expect(project.targets['start:resume'].options.command).toBe('npm run start:resume');
  });

  it('documents the --resume flag and the stale-process killer in the description', () => {
    const desc = project.targets['start:resume'].description;
    expect(desc).toMatch(/--resume/);
    expect(desc).toMatch(/stale/);
  });
});
