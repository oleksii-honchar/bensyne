import * as chokidar from 'chokidar';
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { buildIgnoreRegexes } from '../../application/glob-matcher';

// Integration regression test for the dot-root watch fix (ADR-4, spec §4.4).
//
// The fault: a dot-named source root (e.g. `~/.agent-sessions`) matches its own
// `'**/.*'` exclude pattern. chokidar calls the `ignored` predicate on the root
// BEFORE descending; when it returns true for the root, chokidar does not watch
// anything under it, so NO live `add` events are ever emitted.
//
// A mocked watcher cannot reproduce this. This test uses a REAL chokidar watcher
// on a temp DOT-NAMED root with the same predicate shape as `startWatchingSource`
// (root guard + compiled exclude regexes) and proves the `add` event arrives.
// It is pure fs + chokidar: no Docker, no network, no Mnemosyne, no
// `~/.config/racochu.yaml`, no `~/.agent-sessions`.

// Dot-safe subset of `DEFAULT_IGNORE_GLOBS` from file-watcher.service.ts.
// `**/.*` is the pattern that used to match the dot-named root itself.
const IGNORE_GLOBS: readonly string[] = ['**/.*', '**/.git/**', '**/.DS_Store'];

// Conservative real-fs timing windows (isolated from CI flakiness, ADR-4):
// the watcher must scan + arm, and `awaitWriteFinish` debounces each write.
const WATCHER_READY_WAIT_MS = 5000;
const AWAIT_WRITE_FINISH_STABILITY_MS = 200;
const AWAIT_WRITE_FINISH_POLL_INTERVAL_MS = 50;
const ADD_EVENT_TIMEOUT_MS = 5000;
const NEGATIVE_EXCLUSION_WINDOW_MS = 750;

/**
 * Predicate shape identical to `startWatchingSource` (ADR-1 root guard):
 * the exact normalized root is never excluded; only descendant paths that match
 * an ignore pattern are.
 *
 * RED-PROOF (demonstrated during development): temporarily removing the root
 * guard — `candidatePath.replace(/\/+$/, '') !== normalizedRoot` — makes the
 * root match its own all-dotfile exclude pattern and the `add` assertion in the
 * first test FAILS (chokidar watches nothing under the root). With the guard in
 * place (committed state) the test is GREEN.
 */
function buildIgnoredPredicate(dotRoot: string, ignoreGlobs: readonly string[]): (p: string) => boolean {
  const normalizedRoot = dotRoot.replace(/\/+$/, '');
  const ignoreRegexes = buildIgnoreRegexes([...ignoreGlobs]);
  return (candidatePath: string) =>
    candidatePath.replace(/\/+$/, '') !== normalizedRoot &&
    ignoreRegexes.some(regex => regex.test(candidatePath));
}

/**
 * Resolves once the chokidar watcher is `ready` (initial scan complete; not a
 * proxy for file-out events — `ignoreInitial: true` is always set). Rejects on
 * timeout or on a chokidar 'error' event.
 */
function waitForWatcherReady(watcher: chokidar.FSWatcher, timeoutMs: number): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => {
      watcher.off('ready', onReady);
      reject(new Error(`Timed out after ${timeoutMs}ms waiting for chokidar 'ready' event`));
    }, timeoutMs);
    const onReady = (): void => {
      clearTimeout(timeout);
      resolve();
    };
    watcher.on('ready', onReady);
    watcher.on('error', (error: unknown) => {
      clearTimeout(timeout);
      reject(error instanceof Error ? error : new Error(String(error)));
    });
  });
}

/**
 * Resolves with the absolute path when chokidar emits 'add' for `targetPath`,
 * rejects on timeout. Used for the positive (expect add) assertion.
 */
function waitForAddEvent(
  watcher: chokidar.FSWatcher,
  targetPath: string,
  timeoutMs: number,
): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const timeout = setTimeout(() => {
      watcher.off('add', onAdd);
      reject(new Error(`Timed out after ${timeoutMs}ms waiting for chokidar 'add' event for ${targetPath}`));
    }, timeoutMs);
    const onAdd = (eventPath: string): void => {
      if (eventPath === targetPath) {
        clearTimeout(timeout);
        watcher.off('add', onAdd);
        resolve(eventPath);
      }
    };
    watcher.on('add', onAdd);
  });
}

/**
 * Collects every chokidar 'add' event path that fires within `windowMs`. Used for
 * the negative (expect NO add for an excluded descendant) assertion.
 */
function collectAddEventsForMs(watcher: chokidar.FSWatcher, windowMs: number): Promise<string[]> {
  return new Promise<string[]>(resolve => {
    const fired: string[] = [];
    const onAdd = (eventPath: string): void => {
      fired.push(eventPath);
    };
    watcher.on('add', onAdd);
    setTimeout(() => {
      watcher.off('add', onAdd);
      resolve(fired);
    }, windowMs);
  });
}

describe('[E2E] Watcher dot-root regression — real chokidar on a dot-named root', () => {
  let dotRoot: string;
  let watcher: chokidar.FSWatcher;
  let cleanedUp = false;

  beforeAll(async () => {
    // Dot-named temp dir — the crux: `'**/.*'` would exclude the root itself
    // without the root guard.
    dotRoot = await fs.mkdtemp(path.join(os.tmpdir(), '.racochu-dot-root-'));
    watcher = chokidar.watch(dotRoot.replace(/\/+$/, ''), {
      ignored: buildIgnoredPredicate(dotRoot, IGNORE_GLOBS),
      persistent: true,
      ignoreInitial: true,
      awaitWriteFinish: {
        stabilityThreshold: AWAIT_WRITE_FINISH_STABILITY_MS,
        pollInterval: AWAIT_WRITE_FINISH_POLL_INTERVAL_MS,
      },
    });
    await waitForWatcherReady(watcher, WATCHER_READY_WAIT_MS);
  }, WATCHER_READY_WAIT_MS + 10000);

  afterAll(async () => {
    // Even on assertion failure: close the watcher and remove the temp dir.
    if (watcher != null) {
      watcher.removeAllListeners();
      await watcher.close();
    }
    if (dotRoot != null && !cleanedUp) {
      cleanedUp = true;
      try {
        await fs.rm(dotRoot, { recursive: true, force: true });
      } catch {
        // Best-effort cleanup — never mask the original failure.
      }
    }
  });

  it(
    'emits an add event for a probe file written inside the dot-named root (regression: root must NOT be excluded)',
    async () => {
      // Regression proof: WITHOUT the root guard, chokidar never watches the dot
      // root and this add event never fires. WITH the guard it arrives within ~5s.
      const probePath = path.join(dotRoot, 'probe.md');
      const addPromise = waitForAddEvent(watcher, probePath, ADD_EVENT_TIMEOUT_MS);
      await fs.writeFile(probePath, 'dot-root probe\n', 'utf-8');
      const eventPath = await addPromise;
      expect(eventPath).toBe(probePath);
    },
    ADD_EVENT_TIMEOUT_MS + 15000,
  );

  it(
    'does NOT emit an add event for a file written inside an excluded descendant (.git/)',
    async () => {
      // The root guard must not break descendant exclusion: `'**/.git/**'` (and the
      // dot-dir matcher) still excludes everything under the `.git/` directory.
      await fs.mkdir(path.join(dotRoot, '.git'), { recursive: true });
      const excludedProbePath = path.join(dotRoot, '.git', 'probe.md');
      await fs.writeFile(excludedProbePath, 'should not be watched\n', 'utf-8');

      const fired = await collectAddEventsForMs(watcher, NEGATIVE_EXCLUSION_WINDOW_MS);
      const excludedEvents = fired.filter(p => p === excludedProbePath);
      expect(excludedEvents).toHaveLength(0);
    },
    NEGATIVE_EXCLUSION_WINDOW_MS + 10000,
  );
});
