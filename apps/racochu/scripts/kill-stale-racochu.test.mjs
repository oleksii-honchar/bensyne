import { describe, expect, it, jest } from '@jest/globals';

/**
 * Unit tests for scripts/kill-stale-racochu.mjs (stale racochu zombie killer).
 *
 * These tests are intentionally written RED-first: the script did not exist when
 * they were created (the dynamic import failed with "Cannot find module"). They
 * assert matching/kill BEHAVIOR only — never logger calls.
 *
 * Run with: npm test (chains `jest --config jest.scripts.config.cjs` for the
 * dependency-free ESM scripts suite).
 */
const mod = await import('./kill-stale-racochu.mjs');

describe('parsePsOutput', () => {
  it('parses pid/ppid/command rows and ignores blank lines', () => {
    const text = [
      '  1     0 /sbin/launchd',
      ' 100     1 node dist/src/main.js --resume',
      ' 101     1 /usr/bin/node /opt/app/dist/src/main.js',
      '',
      ' 102   100 node -r ts-node/register -r tsconfig-paths/register src/main.ts',
    ].join('\n');

    expect(mod.parsePsOutput(text)).toEqual([
      { pid: 1, ppid: 0, command: '/sbin/launchd' },
      { pid: 100, ppid: 1, command: 'node dist/src/main.js --resume' },
      { pid: 101, ppid: 1, command: '/usr/bin/node /opt/app/dist/src/main.js' },
      { pid: 102, ppid: 100, command: 'node -r ts-node/register -r tsconfig-paths/register src/main.ts' },
    ]);
  });
});

describe('isRacochuRuntime', () => {
  it('matches compiled entrypoint dist/src/main.js (relative path)', () => {
    expect(mod.isRacochuRuntime('node dist/src/main.js')).toBe(true);
    expect(mod.isRacochuRuntime('node dist/src/main.js --force-reprocess')).toBe(true);
    expect(mod.isRacochuRuntime('node dist/src/main.js --resume')).toBe(true);
  });

  it('matches compiled entrypoint with an absolute path', () => {
    expect(mod.isRacochuRuntime('/usr/bin/node /Users/x/www/olho/bensyne/apps/racochu/dist/src/main.js')).toBe(true);
    expect(mod.isRacochuRuntime('node /opt/apps/racochu/dist/src/main.js --resume')).toBe(true);
  });

  it('matches dev entrypoint src/main.ts only when a ts-node/tsconfig-paths register is present', () => {
    expect(mod.isRacochuRuntime('node -r ts-node/register -r tsconfig-paths/register src/main.ts')).toBe(true);
    expect(mod.isRacochuRuntime('node -r ts-node/register -r tsconfig-paths/register src/main.ts --resume')).toBe(true);
    expect(mod.isRacochuRuntime('node -r tsconfig-paths/register /Users/x/apps/racochu/src/main.ts')).toBe(true);
    // src/main.ts without a register shim is NOT a racochu runtime
    expect(mod.isRacochuRuntime('node src/main.ts')).toBe(false);
  });

  it('rejects unrelated node processes and non-racochu entrypoints', () => {
    const unrelated = [
      'node dist/src/worker.js',
      'node dist/src/main.js.map', // source map is not the entrypoint
      'node main.js',
      'node src/other.ts',
      '/Users/x/.nvm/versions/node/v26.3.0/bin/node --conditions @org/source node_modules/nx/dist/src/daemon/server/start.js',
      '/Users/x/.codex/mcp-servers/chrome-devtools-mcp/node_modules/@browserbasehq/stagehand/dist/index.js',
      'octocode-mcp',
      'mermaid-mcp',
      'python3 -m bensyne_mcp',
      'python3 /Users/x/www/olho/bensyne/apps/bensyne-mcp/main.py',
      'ps -axo pid=,ppid=,command=',
    ];
    for (const cmd of unrelated) {
      expect(mod.isRacochuRuntime(cmd)).toBe(false);
    }
  });
});

describe('collectAncestors', () => {
  it('walks the ppid chain from the given pid up to pid 1', () => {
    const processes = mod.parsePsOutput(
      [
        '  1     0 /sbin/launchd',
        ' 200     1 zsh',
        ' 201   200 npm run start',
        ' 202   201 node scripts/kill-stale-racochu.mjs',
        ' 203   202 sh -c node scripts/kill-stale-racochu.mjs && node dist/src/main.js',
      ].join('\n'),
    );

    expect(mod.collectAncestors(processes, 203)).toEqual([202, 201, 200, 1]);
  });

  it('returns an empty list when the pid has no known ancestors', () => {
    expect(mod.collectAncestors([{ pid: 1, ppid: 0, command: 'launchd' }], 999)).toEqual([]);
  });
});

describe('findStalePids', () => {
  // Fixture defined at module level (describe bodies run before beforeAll).
  const PS_TEXT = [
    '  1     0 /sbin/launchd',
    ' 300   200 node dist/src/main.js --resume',
    ' 301   200 /usr/bin/node /opt/app/racochu/dist/src/main.js',
    ' 302   200 node -r ts-node/register -r tsconfig-paths/register src/main.ts',
    ' 303   200 node -r tsconfig-paths/register /Users/x/apps/racochu/src/main.ts --resume',
    ' 304   200 node dist/src/worker.js',
    ' 305   200 node src/main.ts',
    ' 306   200 node dist/src/main.js.map',
    ' 307   200 node main.js',
    ' 308     1 node --conditions @org/source node_modules/nx/dist/src/daemon/server/start.js',
    ' 309     1 python3 -m bensyne_mcp',
  ].join('\n');

  it('returns exactly the stale racochu PIDs (compiled + dev), excluding unrelated node processes', () => {
    expect(mod.findStalePids(mod.parsePsOutput(PS_TEXT), new Set([1]))).toEqual([300, 301, 302, 303]);
  });

  it('never returns the killer own PID or its ancestor chain even if their command matches', () => {
    // PID 300 is the killer itself; 301 is its ancestor (e.g. a wrapper running dist/src/main.js)
    expect(mod.findStalePids(mod.parsePsOutput(PS_TEXT), new Set([1, 300, 301]))).toEqual([302, 303]);
  });

  it('handles protected pids as a set and always protects pid 1', () => {
    // Only pid 302 is unprotected here
    expect(mod.findStalePids(mod.parsePsOutput(PS_TEXT), new Set([1, 300, 301, 303]))).toEqual([302]);
  });
});

describe('killStalePids', () => {
  it('issues SIGTERM to every stale pid, then SIGKILL only survivors after the grace period, and exits 0', async () => {
    const kills = [];
    const killFn = (pid, signal) => kills.push([pid, signal]);
    const sleepFn = jest.fn(async () => undefined);
    // pid 3 exits on its own after SIGTERM; pid 2 survives and must be SIGKILLed
    const isAliveFn = (pid) => pid !== 3;

    const code = await mod.killStalePids([2, 3], { killFn, sleepFn, isAliveFn, termGraceMs: 8000 });

    expect(kills).toEqual([
      [2, 'SIGTERM'],
      [3, 'SIGTERM'],
      [2, 'SIGKILL'],
    ]);
    expect(sleepFn).toHaveBeenCalledWith(8000);
    expect(code).toBe(0);
  });

  it('never escalates to SIGKILL when every pid exits after SIGTERM', async () => {
    const kills = [];
    const code = await mod.killStalePids([10, 11], {
      killFn: (pid, signal) => kills.push([pid, signal]),
      sleepFn: async () => undefined,
      isAliveFn: () => false,
      termGraceMs: 8000,
    });

    expect(kills).toEqual([
      [10, 'SIGTERM'],
      [11, 'SIGTERM'],
    ]);
    expect(code).toBe(0);
  });

  it('returns exit code 0 even when kill calls throw (never blocks && chaining)', async () => {
    const killFn = () => {
      throw new Error('ESRCH');
    };
    const code = await mod.killStalePids([1, 2], {
      killFn,
      sleepFn: async () => undefined,
      isAliveFn: () => true,
      termGraceMs: 8000,
    });

    expect(code).toBe(0);
  });

  it('does nothing and exits 0 when there are no stale pids', async () => {
    const killFn = jest.fn();
    const code = await mod.killStalePids([], { killFn, sleepFn: async () => undefined, termGraceMs: 8000 });

    expect(killFn).not.toHaveBeenCalled();
    expect(code).toBe(0);
  });
});
