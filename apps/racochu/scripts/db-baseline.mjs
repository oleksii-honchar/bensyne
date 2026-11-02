#!/usr/bin/env node
/**
 * db:baseline — idempotent operator script for the first-deploy P3005 condition.
 *
 * Encodes the proven manual procedure (operator-live-migrations-261101.md) as a
 * bounded decision tree so a second machine hitting `P3005 database schema is
 * not empty` can be fixed with `npm run db:baseline` instead of hand-run prisma
 * commands. NEVER destructive, never `db push`, zero guessing: only the two
 * signals that are known-reconcilable from the recorded procedure may auto-
 * resolve; anything else stops loudly with nothing resolved and exit 1.
 *
 * Decision tree (all effects via injectable exec; decision is a pure function):
 *  0. Optional pre-run safety backup: sqlite3 ".backup" to
 *     data/db-baseline-backup-<UTC ts>.db when the sqlite3 CLI exists
 *     (skipped with a visible note when it does not; `--no-backup` skips it).
 *     Backup files are KEPT (rollback asset; data/ is git-ignored).
 *  (a) probe with `prisma migrate deploy` → already current → report and exit 0.
 *  (b) P3005 → `migrate resolve --applied 0_init` (metadata-only) → re-deploy.
 *  (c) duplicate-column on a KNOWN reconcilable column (skipReason →
 *      20261031_add_skip_reason) → FIRST prove `migrate diff
 *      --from-config-datasource --to-schema prisma/schema.prisma --exit-code`
 *      reports no drift → only then resolve that migration (metadata-only) →
 *      final deploy.
 *  (d) duplicate-column but drift proof is DIRTY → exit 1, zero resolves.
 *  (e) any other failure (unknown error, unknown column, repeat failure after
 *      a resolve) → exit 1, zero further resolves. Refusing to guess is the
 *      designed behavior; a human decides.
 *
 * Always logs its decisions and FileTracker row counts before/after (dry-run-
 * like transparency). Plain Node ESM, zero deps, no build step — consistent
 * with the repo's other scripts. Run from apps/racochu via `npm run db:baseline`.
 */
import { spawnSync } from 'node:child_process';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

/** App-relative paths (all commands run from apps/racochu, like sibling scripts). */
export const DB_PATH = './data/racochu.db';
export const BACKUP_DIR = 'data';
export const FILETRACKER_COUNT_SQL = 'SELECT count(*) FROM FileTracker;';

/** Exact CLI contract the drift proof must use (operator-proven flags). */
export const MIGRATE_DIFF_ARGS = [
  'prisma',
  'migrate',
  'diff',
  '--from-config-datasource',
  '--to-schema',
  'prisma/schema.prisma',
  '--exit-code',
];

/** P3005 ("database schema is not empty") → the baseline migration marker. */
export const BASELINE_MIGRATION = '0_init';

/**
 * The ONLY duplicate-column signals this script may ever auto-resolve
 * (lowercased column name → metadata-only resolve target). Anything else is
 * `unknown` — guessing forbidden.
 */
export const RECONCILABLE_DUPLICATE_COLUMNS = Object.freeze({
  skipreason: '20261031_add_skip_reason',
});

const P3005_RE = /P3005/;
const DUPLICATE_COLUMN_RE = /duplicate column name:\s*'?([A-Za-z_][A-Za-z0-9_]*)'?/i;
const NO_PENDING_RE = /no pending migrations to apply/i;

/**
 * Pure decision over probe signals — no effects, no I/O.
 *
 * @param {{ deployCode: number, deployText: string, driftCode?: number|undefined }} signals
 * @returns {{ action: 'success', alreadyCurrent: boolean }
 *          | { action: 'resolve-applied', migration: string }
 *          | { action: 'prove-drift', migration: string, column: string }
 *          | { action: 'fail', kind: 'drift-dirty' | 'unknown' }}
 */
export function decideDbBaseline({ deployCode, deployText, driftCode }) {
  const text = String(deployText ?? '');
  if (deployCode === 0) {
    return { action: 'success', alreadyCurrent: NO_PENDING_RE.test(text) };
  }
  if (P3005_RE.test(text)) {
    return { action: 'resolve-applied', migration: BASELINE_MIGRATION };
  }
  const dup = text.match(DUPLICATE_COLUMN_RE);
  if (dup) {
    const column = dup[1];
    const migration = RECONCILABLE_DUPLICATE_COLUMNS[column.toLowerCase()];
    if (!migration) return { action: 'fail', kind: 'unknown' }; // unknown column — never guess
    if (driftCode === undefined) return { action: 'prove-drift', migration, column };
    if (driftCode === 0) return { action: 'resolve-applied', migration };
    return { action: 'fail', kind: 'drift-dirty' };
  }
  return { action: 'fail', kind: 'unknown' };
}

function formatTs(date) {
  const p = (n) => String(n).padStart(2, '0');
  return (
    `${date.getUTCFullYear()}${p(date.getUTCMonth() + 1)}${p(date.getUTCDate())}` +
    `-${p(date.getUTCHours())}${p(date.getUTCMinutes())}${p(date.getUTCSeconds())}`
  );
}

function defaultExec(cwd, cmd, args) {
  const r = spawnSync(cmd, args, { cwd, encoding: 'utf8' });
  return { code: r.status ?? 1, stdout: r.stdout ?? '', stderr: r.stderr ?? '' };
}

function probeSqlite3(cwd) {
  const r = spawnSync('sqlite3', ['--version'], { cwd, encoding: 'utf8' });
  return r.status === 0;
}

/**
 * Orchestrator — every external effect goes through `exec`; decision logic is
 * confined to decideDbBaseline. Returns the process exit code.
 */
export async function dbBaselineMain(opts = {}) {
  const {
    argv = [],
    cwd = process.cwd(),
    now = () => new Date(),
    log = (line) => process.stdout.write(`${line}\n`),
  } = opts;
  const exec = opts.exec ?? defaultExec;

  const noBackup = argv.includes('--no-backup');
  const sqlite3Available = opts.sqlite3Available ?? probeSqlite3(cwd);

  // 0) safety backup BEFORE any probing/DDL, when possible and not opted out
  if (noBackup) {
    log('[db-baseline] --no-backup given: skipping the pre-run backup.');
  } else if (!sqlite3Available) {
    // DESIGN CHOICE: proceed without a backup — the only mutating steps below
    // are metadata-only `migrate resolve` writes, all DDL safety comes from the
    // drift proof, and requiring the sqlite3 CLI would lock out hosts that
    // lack it (payfit-class machines). The skip is logged, never silent.
    log('[db-baseline] note: sqlite3 CLI not available — skipping the pre-run backup and continuing.');
  } else {
    const backupPath = `${BACKUP_DIR}/db-baseline-backup-${formatTs(now())}.db`;
    // Real sqlite3 CLI contract (live-proven 261102): the dot-command and its
    // FILENAME must be passed as ONE argv item — '.backup <path>'.
    const backup = exec(cwd, 'sqlite3', [DB_PATH, `.backup ${backupPath}`]);
    if (backup.code !== 0) {
      log(`[db-baseline] ERROR: backup failed (${backup.stderr || backup.stdout || `exit ${backup.code}`}) — refusing to continue without it.`);
      return 1;
    }
    log(`[db-baseline] backup taken: ${backupPath} (kept for rollback; data/ is git-ignored)`);
  }

  const fileTrackerCount = () => {
    if (!sqlite3Available) return 'unavailable (sqlite3 CLI not found)';
    const r = exec(cwd, 'sqlite3', [DB_PATH, FILETRACKER_COUNT_SQL]);
    return r.code === 0 ? r.stdout.trim() : `unknown (count query exit ${r.code})`;
  };

  const before = fileTrackerCount();
  log(`[db-baseline] FileTracker row count before=${before}`);

  // Decision loop: bounded — every known reconcile may run once; a repeat stop-s loudly.
  const resolved = new Set();
  let alreadyCurrent = false;
  const MAX_STEPS = 4;
  for (let step = 0; step < MAX_STEPS; step += 1) {
    const probe = exec(cwd, 'npx', ['prisma', 'migrate', 'deploy']);
    const probeText = probe.stdout + probe.stderr;
    let decision = decideDbBaseline({ deployCode: probe.code, deployText: probeText });

    if (decision.action === 'prove-drift') {
      log(
        `[db-baseline] deploy hit duplicate column '${decision.column}' (reconcilable via ${decision.migration}) — ` +
          'running drift proof BEFORE any resolve: npx prisma migrate diff --from-config-datasource --to-schema prisma/schema.prisma --exit-code',
      );
      const drift = exec(cwd, 'npx', MIGRATE_DIFF_ARGS);
      decision = decideDbBaseline({
        deployCode: probe.code,
        deployText: probeText,
        driftCode: drift.code,
      });
      if (decision.action === 'fail' && decision.kind === 'drift-dirty') {
        log(
          '[db-baseline] ERROR: this drift-dirty case needs human review: drift proof exited nonzero — ' +
            `live DB and prisma/schema.prisma differ. NOTHING was auto-resolved; refusing to guess. Exit 1.`,
        );
        log(`[db-baseline] drift proof said: ${(drift.stdout + drift.stderr).trim() || `exit code ${drift.code}`}`);
        return 1;
      }
    }

    if (decision.action === 'fail') {
      log(
        `[db-baseline] ERROR: unknown failure from prisma migrate deploy (exit ${probe.code}) — nothing was auto-resolved. ` +
          'This case is outside the known-reconcilable set; refusing to guess. Exit 1.',
      );
      log(`[db-baseline] prisma said: ${probeText.trim() || '(no output)'}`);
      return 1;
    }

    if (decision.action === 'success') {
      alreadyCurrent = decision.alreadyCurrent;
      break;
    }

    // decision.action === 'resolve-applied'
    if (resolved.has(decision.migration)) {
      log(
        `[db-baseline] ERROR: deploy still failing after marking ${decision.migration} applied — ` +
          'stopping; no blind repeats. Exit 1.',
      );
      log(`[db-baseline] prisma said: ${probeText.trim() || '(no output)'}`);
      return 1;
    }
    const why = P3005_RE.test(probeText) ? `P3005 (schema not empty)` : `duplicate column '${decision.column ?? decision.migration}' drift-proven clean`;
    log(`[db-baseline] decision: ${why} → marking ${decision.migration} applied (metadata-only), then re-deploying.`);
    const resolve = exec(cwd, 'npx', ['prisma', 'migrate', 'resolve', '--applied', decision.migration]);
    if (resolve.code !== 0) {
      log(`[db-baseline] ERROR: migrate resolve for ${decision.migration} failed (exit ${resolve.code}): ${(resolve.stdout + resolve.stderr).trim()}`);
      return 1;
    }
    resolved.add(decision.migration);
  }

  const after = fileTrackerCount();
  log(`[db-baseline] FileTracker row count after=${after}`);

  if (alreadyCurrent && resolved.size === 0) {
    log('[db-baseline] already up to date — no changes made (no-op).');
  } else if (resolved.size > 0) {
    log(`[db-baseline] reconciled metadata-only: ${[...resolved].join(', ')}; final migrate deploy is clean.`);
  } else {
    log('[db-baseline] pending migrations applied successfully by prisma migrate deploy.');
  }
  return 0;
}

/** CLI entrypoint. */
export async function main() {
  process.exitCode = await dbBaselineMain({ argv: process.argv.slice(2) });
}

const isMain =
  typeof process.argv[1] === 'string' && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  main().catch((err) => {
    process.stderr.write(
      `[db-baseline] ERROR: unexpected failure: ${err && err.stack ? err.stack : err}\n`,
    );
    process.exitCode = 1;
  });
}
