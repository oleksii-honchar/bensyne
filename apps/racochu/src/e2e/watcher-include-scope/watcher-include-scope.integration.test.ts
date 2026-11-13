import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { WatchSourceConfig } from '@/infrastructure/config/config-schemas';
import { ConfigurationService } from '@/infrastructure/config/configuration.service';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { BensyneClient } from '@/infrastructure/services/bensyne-client.service';
import { FileWatcherService } from '@/infrastructure/services/file-watcher.service';
import { ProcessFileUseCase } from '@/use-cases/process-file.use-case';
import { aProcessFileUseCase } from '@/use-cases/process-file.use-case.test-utils';
import { Result } from '@/utils/result';
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';

// E2E regression for the EP1 directory-blindfold hazard (spec §5 EP1, ADR-4,
// risk R2) with the include allow-list wired at the HANDLER level.
//
// The hazard: if include were added to chokidar's `ignored` predicate, extension
// patterns (e.g. '**/*.md', normalized to '**/**\/*.md') would match NO
// directory path — ignored(dir)=true for every directory — and chokidar would
// descend into nothing: the watcher would go blind. A test that mirrors the
// predicate in a copy could not catch that; this suite drives the REAL
// FileWatcherService (real chokidar, compiled predicate, root guard, and
// handler-level scope skip) over a real temp DOT-NAMED root, with the
// processing pipeline represented by a spy sink on ProcessFileUseCase.execute.
//
// It is pure fs + chokidar + the watcher service with stubbed dependencies:
// no network, no Mnemosyne, no `~/.config/racochu.yaml`, no `~/.agent-sessions`
// (same isolation contract as e2e/watcher-dot-root).

// Conservative real-fs timing windows, mirroring watcher-dot-root.integration.test.ts.
const PIPELINE_READY_WAIT_MS = 5000;
const DEBOUNCE_STABILITY_MS = 200; // source.debounceMs → awaitWriteFinish.stabilityThreshold
const ADD_EVENT_TIMEOUT_MS = 5000;
const NEGATIVE_EXCLUSION_WINDOW_MS = 750;

interface DeliveredEvent {
  filePath: string;
  eventType: string;
}

describe('[E2E] Watcher include-scope — real watcher, handler-level include filter, no directory blindfold', () => {
  let dotRoot: string;
  let service: FileWatcherService;
  let sink: ReturnType<typeof aProcessFileUseCase>;
  let delivered: DeliveredEvent[];
  let cleanedUp = false;

  /**
   * Resolves once the sink has recorded an execution for `targetPath` — the
   * pipeline-level equivalent of awaiting chokidar 'ready' plus handler
   * liveness (the service owns the watcher, so the ready event itself is not
   * addressable from outside; the sentinel reaching the sink proves both).
   * Rejects on timeout.
   */
  function waitForPipelineDelivery(targetPath: string, timeoutMs: number): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const deadline = Date.now() + timeoutMs;
      const poll = setInterval(() => {
        if (delivered.some(evt => evt.filePath === targetPath)) {
          clearInterval(poll);
          resolve();
        } else if (Date.now() > deadline) {
          clearInterval(poll);
          reject(new Error(`Timed out after ${timeoutMs}ms waiting for pipeline delivery of ${targetPath}`));
        }
      }, 50);
    });
  }

  /** Resolves with every sink event recorded after `fromIndex` within `windowMs`. */
  function collectDeliveriesForMs(fromIndex: number, windowMs: number): Promise<DeliveredEvent[]> {
    return new Promise<DeliveredEvent[]>(resolve => {
      setTimeout(() => {
        resolve(delivered.slice(fromIndex));
      }, windowMs);
    });
  }

  beforeAll(async () => {
    // Dot-named temp root (mirrors watcher-dot-root): hard guards and dot-dir
    // semantics stay in play exactly as in production.
    dotRoot = await fs.mkdtemp(path.join(os.tmpdir(), '.racochu-include-scope-'));

    // Scope config per the task brief: md-only allow-list + a residual
    // directory exclude (spec §7.1 shape, pointed at a fixture dir of ours).
    // 'plans/' stays UN-excluded on purpose — it is the descent proof.
    const source: WatchSourceConfig = {
      ...aWatchSourceConfig({
        id: 'e2e-include-scope',
        path: dotRoot,
        exclude: ['**/junk-drawers/**'],
        debounceMs: DEBOUNCE_STABILITY_MS,
        memoryBank: 'e2e-include-scope',
      }),
      include: ['**/*.md'],
    };

    delivered = [];
    sink = aProcessFileUseCase();
    sink.execute.mockImplementation(params => {
      const p = params as { filePath: string; eventType: string };
      delivered.push({ filePath: p.filePath, eventType: p.eventType });
      return Promise.resolve(Result.ok(undefined as unknown as void));
    });

    // Stub collaborators: only the FileWatcherService + chokidar + real fs
    // under test are real. start() is called directly, so BensyneClient is
    // never touched (registration lives in onApplicationBootstrap).
    const configService = { getWatchSources: () => [source] } as unknown as ConfigurationService;
    const bensyneClient = {
      initialize: jest.fn(),
      registerBank: jest.fn(),
    } as unknown as BensyneClient;
    const noOpLogger = {
      child: () => noOpLogger,
      debug: jest.fn(),
      info: jest.fn(),
      warn: jest.fn(),
      error: jest.fn(),
    } as unknown as BasePinoLogger;

    service = new FileWatcherService(
      configService,
      sink as unknown as ProcessFileUseCase,
      bensyneClient,
      noOpLogger,
    );
    await service.start();

    // Pipeline-readiness sentinel: written AFTER start(), so its delivery can
    // only happen once the watcher has scanned, armed, and the handlers are
    // live on this root (ignoreInitial would have swallowed pre-existing files).
    const sentinelPath = path.join(dotRoot, 'sentinel.md');
    const sentinelReady = waitForPipelineDelivery(sentinelPath, PIPELINE_READY_WAIT_MS);
    await fs.writeFile(sentinelPath, 'include-scope sentinel\n', 'utf-8');
    await sentinelReady;
  }, PIPELINE_READY_WAIT_MS + 15000);

  afterAll(async () => {
    // Even on assertion failure: stop watchers and remove the temp dir.
    if (service != null) {
      try {
        await service.stop();
      } catch {
        // Best-effort cleanup — never mask the original failure.
      }
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
    'delivers include-matching md files to the pipeline, including one under nested dirs that match no include pattern (no directory blindfold)',
    async () => {
      const rootMdPath = path.join(dotRoot, 'notes.md');
      // 'plans' and '2026' match NO include pattern; as DIRECTORIES they would
      // all be ignored if include ever entered the `ignored` predicate —
      // delivering this file proves descent happened (the exact §5 hazard).
      const nestedMdPath = path.join(dotRoot, 'plans', '2026', 'nested.md');
      await fs.mkdir(path.dirname(nestedMdPath), { recursive: true });

      const rootDelivered = waitForPipelineDelivery(rootMdPath, ADD_EVENT_TIMEOUT_MS);
      const nestedDelivered = waitForPipelineDelivery(nestedMdPath, ADD_EVENT_TIMEOUT_MS);
      await fs.writeFile(rootMdPath, '# root notes\n', 'utf-8');
      await fs.writeFile(nestedMdPath, '# nested notes\n', 'utf-8');
      await Promise.all([rootDelivered, nestedDelivered]);

      // Both include-matching files reached the pipeline (the nested one under
      // directories no include pattern matches = no directory blindfold).
      const allDeliveredPaths = new Set(delivered.map(e => e.filePath));
      expect(allDeliveredPaths.has(rootMdPath)).toBe(true);
      expect(allDeliveredPaths.has(nestedMdPath)).toBe(true);
      // Their deliveries carry add semantics (scoped to these two paths — the
      // readiness sentinel's event kind is not part of any contract and may
      // race between add/change when the write overlaps the initial scan).
      const addEvents = delivered.filter(e => e.eventType === 'add').map(e => e.filePath);
      expect(new Set(addEvents.filter(p => p === rootMdPath || p === nestedMdPath))).toEqual(
        new Set([rootMdPath, nestedMdPath]),
      );
    },
    ADD_EVENT_TIMEOUT_MS + 15000,
  );

  it(
    'never delivers non-matching extensions, hard-guarded .git md, or md inside an excluded directory',
    async () => {
      const baseline = delivered.length;

      // include-non-matching file:
      await fs.writeFile(path.join(dotRoot, 'data.txt'), 'not markdown\n', 'utf-8');
      await fs.writeFile(path.join(dotRoot, 'notes.sample'), 'sample junk\n', 'utf-8');
      // hard-guard path that WOULD match the include by extension (I1 — include
      // never re-admits a hard-guard path):
      await fs.mkdir(path.join(dotRoot, '.git'), { recursive: true });
      await fs.writeFile(path.join(dotRoot, '.git', 'config.md'), 'guarded\n', 'utf-8');
      // .md inside an excluded directory (residual exclude — exclude wins):
      await fs.mkdir(path.join(dotRoot, 'junk-drawers'), { recursive: true });
      await fs.writeFile(path.join(dotRoot, 'junk-drawers', 'ghost.md'), 'excluded\n', 'utf-8');

      const added = await collectDeliveriesForMs(baseline, NEGATIVE_EXCLUSION_WINDOW_MS);
      const newPaths = new Set(added.map(e => e.filePath));

      expect(newPaths.has(path.join(dotRoot, 'data.txt'))).toBe(false);
      expect(newPaths.has(path.join(dotRoot, 'notes.sample'))).toBe(false);
      expect(newPaths.has(path.join(dotRoot, '.git', 'config.md'))).toBe(false);
      expect(newPaths.has(path.join(dotRoot, 'junk-drawers', 'ghost.md'))).toBe(false);

      // md-only processing across the WHOLE run: the pipeline never saw any
      // path other than the three include-matching md files (event-kind-agnostic
      // set — any event for any other path would break this).
      const allDeliveredPaths = new Set(delivered.map(e => e.filePath));
      expect(allDeliveredPaths).toEqual(
        new Set([
          path.join(dotRoot, 'sentinel.md'),
          path.join(dotRoot, 'notes.md'),
          path.join(dotRoot, 'plans', '2026', 'nested.md'),
        ]),
      );
    },
    NEGATIVE_EXCLUSION_WINDOW_MS + 10000,
  );
});
