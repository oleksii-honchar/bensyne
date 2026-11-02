import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from '@jest/globals';

/**
 * Unit tests for scripts/db-baseline.mjs — idempotent operator script for the
 * first-deploy P3005 condition (Ad-Hoc Task C).
 *
 * Written RED-first: the script did not exist when this file was created (the
 * dynamic import failed with "Cannot find module"). Test groups map 1:1 to the
 * brief's decision-tree branches (a)-(e) plus --no-backup and the hard rule
 * that the drift proof ALWAYS precedes the 20261031_add_skip_reason resolve.
 *
 * Decision (pure function decideDbBaseline over signals) is separated from
 * effects (all process execution goes through the injected `exec`); these tests
 * assert BEHAVIOR only: exit codes, exec call sequences, logged decisions —
 * never logger implementation details.
 *
 * Run with: npm test (chains `jest --config jest.scripts.config.cjs` for the
 * dependency-free ESM scripts suite).
 */
const mod = await import('./db-baseline.mjs');
const { decideDbBaseline, dbBaselineMain } = mod;

/**
 * Fake exec: records `cmd args...` invocations and answers scripted responses.
 * Counts and backup commands are answered generically so tests can script only
 * the prisma-CLI sequence under test.
 */
function makeExec(scenario) {
  const calls = [];
  const rawCalls = [];
  let prismaStep = 0;
  const exec = (_cwd, cmd, args) => {
    rawCalls.push([cmd, ...args]);
    calls.push([cmd, ...args].join(' '));
    const joined = [cmd, ...args].join(' ');
    if (joined.startsWith('sqlite3 ') && args.some((a) => String(a).includes('count(*)'))) {
      return { code: 0, stdout: `${scenario.count ?? 7985}\n`, stderr: '' };
    }
    if (joined.startsWith('sqlite3 ') && args.some((a) => String(a).startsWith('.backup'))) {
      return { code: 0, stdout: '', stderr: '' };
    }
    if (joined.startsWith('npx prisma migrate deploy')) {
      const step = scenario.deploys[prismaStep] ?? scenario.deploys.at(-1);
      prismaStep += 1;
      return { code: step.code, stdout: step.stdout ?? '', stderr: step.stderr ?? '' };
    }
    if (joined.startsWith('npx prisma migrate diff')) {
      return { code: scenario.driftCode ?? 0, stdout: '', stderr: '' };
    }
    if (joined.startsWith('npx prisma migrate resolve')) {
      return { code: 0, stdout: `Migration ${args.at(-1)} marked as applied.`, stderr: '' };
    }
    throw new Error(`unexpected exec in test: ${joined}`);
  };
  return { exec, calls, rawCalls };
}

function makeLog() {
  const lines = [];
  const log = (line) => lines.push(String(line));
  return { log, lines };
}

async function runMain({ scenario, argv = [], sqlite3Available = true }) {
  const { exec, calls, rawCalls } = makeExec(scenario);
  const { log, lines } = makeLog();
  const code = await dbBaselineMain({
    argv,
    exec,
    sqlite3Available,
    now: () => new Date(Date.UTC(2026, 10, 2, 10, 0, 0)),
    log,
  });
  return { code, calls, rawCalls, lines };
}

const noPending = { code: 0, stdout: 'No pending migrations to apply.\n', stderr: '' };
const p3005 = {
  code: 1,
  stdout: '',
  stderr: 'Error: P3005\n\nThe database schema is not empty. Read more in our docs\n',
};
const duplicateColumn = {
  code: 1,
  stdout: '',
  stderr: "Error: Migration query failed: Duplicate column name: 'skipReason'\n",
};

describe('branch (a): database already current → no-op exit 0', () => {
  it('reports already-up-to-date, resolves nothing, and exits 0', async () => {
    const { code, calls, lines } = await runMain({ scenario: { deploys: [noPending] } });

    expect(code).toBe(0);
    expect(calls.filter((c) => c.includes('migrate resolve'))).toEqual([]);
    expect(calls.filter((c) => c.includes('migrate deploy')).length).toBe(1);
    expect(lines.join('\n')).toMatch(/already up to date/i);
  });

  it('logs FileTracker row counts before and after (equal, untouched)', async () => {
    const { code, lines } = await runMain({ scenario: { deploys: [noPending], count: 7985 } });

    expect(code).toBe(0);
    const text = lines.join('\n');
    expect(text).toMatch(/before.*7985/i);
    expect(text).toMatch(/after.*7985/i);
  });
});

describe('branch (b): P3005 → resolve 0_init then redeploy', () => {
  it('resolves 0_init then re-deploys, in exactly that order, and exits 0', async () => {
    const { code, calls } = await runMain({ scenario: { deploys: [p3005, noPending] } });

    expect(code).toBe(0);
    const prismaCalls = calls.filter((c) => c.startsWith('npx prisma '));
    expect(prismaCalls).toEqual([
      'npx prisma migrate deploy',
      'npx prisma migrate resolve --applied 0_init',
      'npx prisma migrate deploy',
    ]);
  });

  it('logs what it decided (P3005 → marked 0_init applied)', async () => {
    const { code, lines } = await runMain({ scenario: { deploys: [p3005, noPending] } });

    expect(code).toBe(0);
    expect(lines.join('\n')).toMatch(/P3005/);
    expect(lines.join('\n')).toMatch(/0_init/);
  });
});

describe('branch (c): duplicate column + drift-PROVEN clean → resolve 20261031_add_skip_reason, final deploy no-op', () => {
  it('deploy → drift proof → resolve → final deploy, in exactly that order, exit 0', async () => {
    const { code, calls } = await runMain({
      scenario: { deploys: [duplicateColumn, noPending], driftCode: 0 },
    });

    expect(code).toBe(0);
    const prismaCalls = calls.filter((c) => c.startsWith('npx prisma '));
    expect(prismaCalls).toEqual([
      'npx prisma migrate deploy',
      'npx prisma migrate diff --from-config-datasource --to-schema prisma/schema.prisma --exit-code',
      'npx prisma migrate resolve --applied 20261031_add_skip_reason',
      'npx prisma migrate deploy',
    ]);
  });

  it('never resolves 20261031_add_skip_reason BEFORE the drift proof has run clean', async () => {
    const { code, calls } = await runMain({
      scenario: { deploys: [duplicateColumn, noPending], driftCode: 0 },
    });

    expect(code).toBe(0);
    const diffIdx = calls.findIndex((c) => c.includes('migrate diff'));
    const resolveIdx = calls.findIndex((c) => c.includes('migrate resolve'));
    expect(diffIdx).toBeGreaterThanOrEqual(0);
    expect(resolveIdx).toBeGreaterThan(diffIdx);
  });

  it('after P3005 was already resolved and a repeat deploy hits duplicate column, the same guarded path applies', async () => {
    // Real mmm6 sequence: P3005 → resolve 0_init → deploy again → duplicate column → drift proof → resolve 20261031.
    const { code, calls } = await runMain({
      scenario: { deploys: [p3005, duplicateColumn, noPending], driftCode: 0 },
    });

    expect(code).toBe(0);
    const prismaCalls = calls.filter((c) => c.startsWith('npx prisma '));
    expect(prismaCalls).toEqual([
      'npx prisma migrate deploy',
      'npx prisma migrate resolve --applied 0_init',
      'npx prisma migrate deploy',
      'npx prisma migrate diff --from-config-datasource --to-schema prisma/schema.prisma --exit-code',
      'npx prisma migrate resolve --applied 20261031_add_skip_reason',
      'npx prisma migrate deploy',
    ]);
  });
});

describe('branch (d): duplicate column + drift-DIRTY → loud exit 1, zero resolves', () => {
  it('stops with a loud drift error and resolves nothing', async () => {
    const { code, calls, lines } = await runMain({
      scenario: { deploys: [duplicateColumn], driftCode: 2 },
    });

    expect(code).toBe(1);
    expect(calls.filter((c) => c.includes('migrate resolve'))).toEqual([]);
    expect(lines.join('\n')).toMatch(/drift/i);
  });

  it('never resolves when the drift proof has not run clean (ordering rule, dirty case)', async () => {
    const { calls } = await runMain({ scenario: { deploys: [duplicateColumn], driftCode: 1 } });

    expect(calls.filter((c) => c.includes('migrate resolve'))).toEqual([]);
  });
});

describe('branch (e): unknown error → loud exit 1, zero resolves (refuse-to-guess)', () => {
  it('stops on an unrelated deploy failure without resolving anything', async () => {
    const unknown = { code: 1, stdout: '', stderr: 'Error: P4001 the schema needed for the import could not be found\n' };
    const { code, calls, lines } = await runMain({ scenario: { deploys: [unknown] } });

    expect(code).toBe(1);
    expect(calls.filter((c) => c.includes('migrate resolve'))).toEqual([]);
    expect(lines.join('\n')).toMatch(/unknown/i);
  });

  it('a duplicate column NOT in the reconcilable set is unknown (guessing forbidden)', async () => {
    const otherDup = { code: 1, stdout: '', stderr: "Error: Migration query failed: Duplicate column name: 'mysteryColumn'\n" };
    const { code, calls } = await runMain({ scenario: { deploys: [otherDup] } });

    expect(code).toBe(1);
    expect(calls.filter((c) => c.includes('migrate resolve'))).toEqual([]);
  });

  it('the same failure right after a resolve stops loudly instead of looping forever', async () => {
    const { code, calls } = await runMain({
      scenario: { deploys: [p3005, p3005, p3005, p3005], driftCode: 0 },
    });

    expect(code).toBe(1);
    // resolve 0_init attempted exactly once — no blind repeats
    expect(calls.filter((c) => c.includes('migrate resolve --applied 0_init'))).toHaveLength(1);
  });
});

describe('backup behavior', () => {
  it('by default with sqlite3 available, takes a .backup into data/db-baseline-backup-<ts>.db BEFORE the first probe', async () => {
    const { code, calls, rawCalls } = await runMain({ scenario: { deploys: [noPending] } });

    expect(code).toBe(0);
    const backupIdx = calls.findIndex((c) => c.includes('.backup'));
    const deployIdx = calls.findIndex((c) => c.includes('migrate deploy'));
    expect(backupIdx).toBeGreaterThanOrEqual(0);
    expect(backupIdx).toBeLessThan(deployIdx);
    // Real sqlite3 CLI contract (live-proven 261102): the dot-command and its
    // FILENAME are ONE argv item ('.backup <path>') — passing them as two args
    // fails on the real CLI with "missing FILENAME argument on .backup".
    expect(rawCalls[backupIdx]).toEqual([
      'sqlite3',
      './data/racochu.db',
      '.backup data/db-baseline-backup-20261102-100000.db',
    ]);
  });

  it('the backup file is KEPT (documented design choice: rollback asset; data/ is git-ignored)', async () => {
    // No effect call ever removes the backup — assert the script issues no rm/unlink/delete.
    const { calls } = await runMain({ scenario: { deploys: [noPending] } });
    const removal = calls.find((c) => /^rm |unlink|DELETE FROM|DROP /i.test(c));
    expect(removal).toBeUndefined();
  });

  it('--no-backup is respected: no sqlite3 .backup call is made', async () => {
    const { code, calls } = await runMain({ scenario: { deploys: [noPending], count: 7985 }, argv: ['--no-backup'] });

    expect(code).toBe(0);
    expect(calls.filter((c) => c.includes('.backup'))).toEqual([]);
  });

  it('when the sqlite3 CLI is unavailable, backup is skipped gracefully with a documented note and the run proceeds', async () => {
    const { code, calls, lines } = await runMain({
      scenario: { deploys: [noPending], count: null },
      sqlite3Available: false,
    });

    expect(code).toBe(0);
    expect(calls.filter((c) => c.startsWith('sqlite3 '))).toEqual([]);
    expect(lines.join('\n')).toMatch(/sqlite3 CLI not (found|available)/i);
    const deployIdx = calls.findIndex((c) => c.includes('migrate deploy'));
    expect(deployIdx).toBeGreaterThanOrEqual(0); // the prisma work still happened
  });
});

describe('purity and safety', () => {
  it('never issues `db push` or destructive SQL through exec, on any branch', async () => {
    const scenarios = [
      { deploys: [noPending] },
      { deploys: [p3005, noPending] },
      { deploys: [duplicateColumn, noPending], driftCode: 0 },
      { deploys: [duplicateColumn], driftCode: 2 },
    ];
    for (const scenario of scenarios) {
      const { calls } = await runMain({ scenario });
      const offenders = calls.filter(
        (c) => /db push/i.test(c) || /\b(DROP TABLE|DROP COLUMN|ALTER TABLE|DELETE FROM|TRUNCATE)\b/i.test(c),
      );
      expect(offenders).toEqual([]);
    }
  });

  it('decideDbBaseline is a pure mapping over signals (no effects, same input → same output)', () => {
    const sig = { deployCode: 1, deployText: p3005.stderr };
    expect(decideDbBaseline(sig)).toEqual(decideDbBaseline(sig));
    expect(decideDbBaseline(sig)).toMatchObject({ action: 'resolve-applied', migration: '0_init' });

    expect(decideDbBaseline({ deployCode: 0, deployText: 'No pending migrations to apply.' })).toMatchObject({
      action: 'success',
    });
    expect(
      decideDbBaseline({ deployCode: 1, deployText: "Duplicate column name: 'skipReason'" }),
    ).toMatchObject({ action: 'prove-drift', migration: '20261031_add_skip_reason' });
    expect(
      decideDbBaseline({
        deployCode: 1,
        deployText: "Duplicate column name: 'skipReason'",
        driftCode: 3,
      }),
    ).toMatchObject({ action: 'fail', kind: 'drift-dirty' });
    expect(decideDbBaseline({ deployCode: 1, deployText: 'Error: P9999 boom' })).toMatchObject({
      action: 'fail',
      kind: 'unknown',
    });
  });
});

describe('wiring: package.json gains exactly one script', () => {
  const pkg = JSON.parse(readFileSync(join(import.meta.dirname, '..', 'package.json'), 'utf8'));

  it('db:baseline exists with the exact command (cwd-resolved like sibling scripts)', () => {
    expect(pkg.scripts['db:baseline']).toBe('node scripts/db-baseline.mjs');
  });
});
