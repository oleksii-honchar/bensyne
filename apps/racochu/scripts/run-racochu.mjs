#!/usr/bin/env node
/**
 * Start a Racochu runtime with the local internal-CA bundle, when available.
 *
 * Node reads NODE_EXTRA_CA_CERTS at process startup. This wrapper therefore
 * selects the PEM before spawning Node, Nodemon, or dotenvx; application code
 * cannot reliably make this change after startup.
 */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

export function localCaCandidates(home = homedir()) {
  return [
    join(home, '.config', 'racochu', 'extra-ca.pem'),
    join(home, '.config', 'better-opencode', 'extra-ca.pem'),
    join(home, '.local', 'share', 'racochu', 'certs', 'litellm-caddy-root.pem'),
  ];
}

export function resolveExtraCaCerts({ env = process.env, exists = existsSync, home = homedir() } = {}) {
  if (env.NODE_EXTRA_CA_CERTS) return env.NODE_EXTRA_CA_CERTS;
  return localCaCandidates(home).find(exists);
}

export function createLaunchEnv(options = {}) {
  const env = options.env ?? process.env;
  const extraCaCerts = resolveExtraCaCerts({ ...options, env });
  return extraCaCerts ? { ...env, NODE_EXTRA_CA_CERTS: extraCaCerts } : { ...env };
}

function waitForChild(child) {
  return new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('exit', (code, signal) => resolve(code ?? (signal ? 1 : 0)));
  });
}

export async function runRacochu({
  command,
  args = [],
  skipCleanup = false,
  env = process.env,
  spawnFn = spawn,
  exists = existsSync,
  home = homedir(),
  cleanupFn,
} = {}) {
  if (!command) throw new Error('A command is required');
  const launchEnv = createLaunchEnv({ env, exists, home });
  const spawnOptions = { env: launchEnv, stdio: 'inherit', shell: process.platform === 'win32' };

  if (!skipCleanup) {
    if (cleanupFn) {
      await cleanupFn(launchEnv);
    } else {
      const cleanup = spawnFn(process.execPath, ['scripts/kill-stale-racochu.mjs'], spawnOptions);
      await waitForChild(cleanup);
    }
  }

  const child = spawnFn(command, args, spawnOptions);
  return waitForChild(child);
}

export async function main(argv = process.argv.slice(2)) {
  const skipCleanup = argv[0] === '--skip-cleanup';
  const [command, ...args] = skipCleanup ? argv.slice(1) : argv;
  process.exitCode = await runRacochu({ command, args, skipCleanup });
}

const isMain = typeof process.argv[1] === 'string' && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  main().catch(error => {
    console.error(`[run-racochu] ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  });
}
