#!/usr/bin/env node
/**
 * Kill stale racochu zombie processes before a new instance starts.
 *
 * Plain Node ESM, zero dependencies, no build step — consistent with the rest
 * of the repo's scripts. Prepended to the racochu npm start scripts via
 * `node scripts/kill-stale-racochu.mjs &&` so a stale `node dist/src/main.js`
 * (e.g. an abandoned --resume) can never linger and interfere with a new one.
 *
 * Behavior:
 *  - Snapshots processes as `pid ppid command` lines. POSIX/Git-Bash uses
 *    `ps -axo pid=,ppid=,command=`; Windows falls back to PowerShell
 *    `Get-CimInstance Win32_Process` (Git Bash `ps` rejects `-axo` and never
 *    sees native node processes, which would silently disable the killer).
 *  - Matches racochu runtime entrypoints: `dist/src/main.js`, or `src/main.ts`
 *    launched with a ts-node/tsconfig-paths register shim (relative OR absolute
 *    paths, forward or backslashes).
 *  - Protects: the killer's own PID, its full ancestor chain (npm/nx/sh/nodemon),
 *    and PID 1. Never touches unrelated node processes.
 *  - SIGTERM each stale PID, wait up to ~8s, then SIGKILL survivors.
 *  - Removes the stale pino-roll `current.log` link afterwards so the new
 *    instance's logging worker never crashes with `EEXIST` on symlink creation.
 *  - ALWAYS exits 0 so `&&` chaining never blocks startup.
 */
import { spawnSync } from 'node:child_process';
import { lstatSync, rmSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

export const PS_ARGS = ['-axo', 'pid=,ppid=,command='];

// Windows fallback: enumerate every process (including native node.exe) and
// emit rows in the same `pid ppid command` shape `parsePsOutput` expects.
export const WIN32_SNAPSHOT_ARGS = [
  '-NoProfile',
  '-Command',
  'Get-CimInstance Win32_Process | ForEach-Object { "{0} {1} {2}" -f $_.ProcessId, $_.ParentProcessId, $_.CommandLine }',
];

// pino-roll hardcodes a `current.log` symlink next to the active log file and
// recreates it on every start. Its check-then-create is not atomic and only
// unlinks pre-existing *symlinks*, so an unexpected state (regular file left
// behind, link retargeted by a rotation, racing writer) crashes the logging
// worker with EEXIST. Deleting it before startup gives a clean slate.
export const CURRENT_LOG_LINK = join(
  homedir(),
  '.local',
  'share',
  'racochu',
  'logs',
  'current.log',
);

// Entrypoint match rules. Trailing lookahead ensures `dist/src/main.js.map`
// (a source map, not the runtime) is never treated as the compiled entrypoint.
const COMPILED_ENTRYPOINT_RE = /dist\/src\/main\.js(?=\s|$)/;
const DEV_ENTRYPOINT_RE = /src\/main\.ts(?=\s|$)/;
const REGISTER_SHIM_RE = /(?:ts-node|tsconfig-paths)\/register/;

/** Parse `ps -axo pid=,ppid=,command=` output into { pid, ppid, command } rows. */
export function parsePsOutput(text) {
  const rows = [];
  for (const rawLine of String(text ?? '').split('\n')) {
    const line = rawLine.trim();
    if (!line) continue;
    const match = line.match(/^(\d+)\s+(\d+)\s+(.*)$/);
    if (!match) continue;
    rows.push({ pid: Number(match[1]), ppid: Number(match[2]), command: match[3] });
  }
  return rows;
}

/** True when a process command looks like a racochu runtime entrypoint. */
export function isRacochuRuntime(command) {
  // Normalize Windows backslash path separators so `dist\src\main.js` matches.
  const cmd = String(command ?? '').replace(/\\/g, '/');
  if (COMPILED_ENTRYPOINT_RE.test(cmd)) return true;
  return DEV_ENTRYPOINT_RE.test(cmd) && REGISTER_SHIM_RE.test(cmd);
}

/**
 * Snapshot all processes as `pid ppid command` text. Returns '' when the
 * platform snapshot tool is unavailable or fails (never blocks startup).
 */
export function snapshotProcesses(spawnFn = spawnSync) {
  if (process.platform === 'win32') {
    const result = spawnFn('powershell', WIN32_SNAPSHOT_ARGS, {
      encoding: 'utf8',
      timeout: 10_000,
      windowsHide: true,
    });
    return result.status === 0 ? result.stdout : '';
  }
  const result = spawnFn('ps', PS_ARGS, { encoding: 'utf8' });
  return result.status === 0 ? result.stdout : '';
}

/**
 * Remove the pino-roll `current.log` link if it exists (any state). pino-roll
 * recreates it on startup. Never throws.
 */
export function removeStaleCurrentLogLink(linkPath = CURRENT_LOG_LINK) {
  try {
    lstatSync(linkPath);
  } catch {
    return false; // absent or inaccessible — nothing to clean
  }
  try {
    rmSync(linkPath, { force: true });
    return true;
  } catch {
    return false;
  }
}

/**
 * Walk the parent chain of `pid` up to PID 1 (inclusive) and return every
 * ancestor PID. Guards against self-loops and missing parents.
 */
export function collectAncestors(processes, pid) {
  const byPid = new Map(processes.map((p) => [p.pid, p]));
  const ancestors = [];
  const seen = new Set([pid]);
  let current = byPid.get(pid);
  while (current) {
    const parent = current.ppid;
    if (seen.has(parent)) break; // cycle / self-parent: stop
    seen.add(parent);
    ancestors.push(parent);
    if (parent === 1) break;
    current = byPid.get(parent);
  }
  return ancestors;
}

/**
 * Given parsed processes and a set of protected PIDs, return the stale racochu
 * runtime PIDs (ascending). Protected PIDs are never returned, even if their
 * command matches.
 */
export function findStalePids(processes, protectedPids) {
  return processes
    .filter((p) => isRacochuRuntime(p.command) && !protectedPids.has(p.pid))
    .map((p) => p.pid)
    .sort((a, b) => a - b);
}

function defaultKill(pid, signal) {
  process.kill(pid, signal);
}

function defaultIsAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function defaultSleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Graceful kill flow: SIGTERM every stale PID, wait up to `termGraceMs` for
 * them to exit, then SIGKILL the survivors. Every kill error is swallowed and
 * the function always resolves 0 so `&&` chaining never blocks startup.
 */
export async function killStalePids(pids, deps = {}) {
  const {
    killFn = defaultKill,
    sleepFn = defaultSleep,
    isAliveFn = defaultIsAlive,
    termGraceMs = 8000,
  } = deps;

  if (pids.length === 0) return 0;

  for (const pid of pids) {
    try {
      killFn(pid, 'SIGTERM');
    } catch {
      // Process may already be gone — fine.
    }
  }

  await sleepFn(termGraceMs);

  for (const pid of pids) {
    let alive = false;
    try {
      alive = isAliveFn(pid);
    } catch {
      alive = false;
    }
    if (!alive) continue;
    try {
      killFn(pid, 'SIGKILL');
    } catch {
      // Process exited between the check and the kill — fine.
    }
  }

  return 0;
}

/**
 * End-to-end orchestration (injectable for tests): parse ps output, build the
 * protected PID set (own PID + ancestors + PID 1), find stale racochu PIDs and
 * kill them. Always resolves 0.
 */
export async function run({ ownPid, psText, ...killDeps }) {
  const processes = parsePsOutput(psText);
  const ancestors = collectAncestors(processes, ownPid);
  const protectedPids = new Set([ownPid, 1, ...ancestors]);
  const stale = findStalePids(processes, protectedPids);

  if (stale.length > 0) {
    console.error(`[kill-stale-racochu] killing stale racochu PIDs: ${stale.join(', ')}`);
  }
  return killStalePids(stale, killDeps);
}

/** CLI entrypoint: snapshot ps, kill stale racochu processes, always exit 0. */
export async function main() {
  const psText = snapshotProcesses();
  const code = await run({ ownPid: process.pid, psText });
  if (removeStaleCurrentLogLink()) {
    console.error(
      '[kill-stale-racochu] removed stale current.log link (pino-roll recreates it on startup)',
    );
  }
  process.exitCode = code;
}

const isMain =
  typeof process.argv[1] === 'string' && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  main().catch(() => {
    process.exitCode = 0; // never block `&&` chaining
  });
}
