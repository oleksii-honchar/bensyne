import { describe, expect, it } from '@jest/globals';

/**
 * Unit tests for scripts/purge-file.mjs (purge an already-ingested file from
 * bensyne + the local racochu tracker DB).
 *
 * These tests assert PURE helper behavior only (arg parsing + config path
 * resolution) — the MCP/DB operations are verified operationally against the
 * real bensyne + local Prisma DB per the task's acceptance criteria.
 * Never asserts logger calls.
 *
 * Run with: npm test (chains `jest --config jest.scripts.config.cjs` for the
 * dependency-free ESM scripts suite).
 */
const mod = await import('./purge-file.mjs');

describe('parseArgs', () => {
  it('parses --file and --bank', () => {
    expect(
      mod.parseArgs([
        '--file',
        '/tmp/merge-tree-output.txt',
        '--bank',
        'agent-sessions',
      ]),
    ).toEqual({
      file: '/tmp/merge-tree-output.txt',
      bank: 'agent-sessions',
      check: false,
      help: false,
    });
  });

  it('supports --check and --help flags', () => {
    expect(
      mod.parseArgs(['--file', '/tmp/a.txt', '--bank', 'b', '--check']),
    ).toEqual({ file: '/tmp/a.txt', bank: 'b', check: true, help: false });

    expect(mod.parseArgs(['--help'])).toEqual({
      file: null,
      bank: null,
      check: false,
      help: true,
    });
  });

  it('rejects missing required args (no --file or no --bank)', () => {
    expect(() => mod.parseArgs(['--bank', 'agent-sessions'])).toThrow(/--file/);
    expect(() => mod.parseArgs(['--file', '/tmp/a.txt'])).toThrow(/--bank/);
  });
});

describe('classifyForgetResponse', () => {
  it('accepts the JSON status no-ops and success shapes', () => {
    expect(mod.classifyForgetResponse({ status: 'forgotten' })).toBe(true);
    expect(mod.classifyForgetResponse({ status: 'already_deleted' })).toBe(true);
    expect(mod.classifyForgetResponse({ status: 'FILE_NOT_FOUND' })).toBe(true);
  });

  it('accepts the real bensyne wire shape for a never-ingested file (tool error text containing FILE_NOT_FOUND)', () => {
    const wire = {
      text: "Error calling tool 'forgetFile': forgetFile failed: FILE_NOT_FOUND — details: {\"path\": \"/tmp/x.txt\"}",
    };
    expect(mod.classifyForgetResponse(wire)).toBe(true);
  });

  it('rejects unknown/unexpected responses', () => {
    expect(mod.classifyForgetResponse({ status: 'forbidden' })).toBe(false);
    expect(mod.classifyForgetResponse({ text: 'some other tool error' })).toBe(false);
    expect(mod.classifyForgetResponse({})).toBe(false);
  });
});

describe('resolveConfigPath', () => {
  const original = process.env.APP_CONFIG_PATH;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.APP_CONFIG_PATH;
    } else {
      process.env.APP_CONFIG_PATH = original;
    }
  });

  it('honors APP_CONFIG_PATH when set (same as the app bootstrap)', () => {
    process.env.APP_CONFIG_PATH = '/tmp/custom.yaml';
    expect(mod.resolveConfigPath()).toBe('/tmp/custom.yaml');
  });

  it('falls back to ~/.config/racochu.yaml when APP_CONFIG_PATH is unset', () => {
    delete process.env.APP_CONFIG_PATH;
    expect(mod.resolveConfigPath()).toBe(
      `${process.env.HOME}/.config/racochu.yaml`,
    );
  });
});
