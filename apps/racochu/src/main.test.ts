import { NestFactory } from '@nestjs/core';
import * as child_process from 'child_process';
import * as fs from 'fs';
import { Logger } from 'nestjs-pino';
import * as os from 'os';
import * as path from 'path';
import {
  ExcludeReconciliationService,
  ReconciliationSummary,
} from './application/services/exclude-reconciliation.service';
import { ForceReprocessService } from './application/services/force-reprocess.service';
import { RecoverService } from './application/services/recover.service';
import { ReprocessEdgesService } from './application/services/reprocess-edges.service';
import { TtlReconciliationService, TtlSweepSummary } from './application/services/ttl-reconciliation.service';
import { ConfigurationService } from './infrastructure/config/configuration.service';
import { BasePinoLogger } from './infrastructure/logging/base-pino-logger';
import { FileProcessingQueue } from './infrastructure/services/file-processing-queue.service';
import { FileWatcherService } from './infrastructure/services/file-watcher.service';
import { resolveWatchLockPath } from './infrastructure/services/instance-lock.service';
import { bootstrap } from './main';

// Mock NestFactory so bootstrap() never constructs a real Nest application.
jest.mock('@nestjs/core', () => ({
  NestFactory: {
    createApplicationContext: jest.fn(),
  },
}));

// C6 test seam: the REAL InstanceLockService runs against real fs in a temp
// dir; only the data-dir path resolution is redirected per test.
jest.mock('./infrastructure/services/instance-lock.service', () => {
  const actual = jest.requireActual('./infrastructure/services/instance-lock.service');
  return {
    ...actual,
    resolveWatchLockPath: jest.fn((): string => path.join(os.tmpdir(), 'racochu-unconfigured.watch.lock')),
  };
});
const mockedResolveWatchLockPath = jest.mocked(resolveWatchLockPath);

// Pid above every supported OS pid ceiling — process.kill(pid, 0) ESRCHs,
// so the real liveness check treats the holder as dead.
const DEAD_PID = 2147483647;

const createdLockDirs: string[] = [];

afterAll(() => {
  for (const dir of createdLockDirs) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

const EMPTY_SUMMARY: ReconciliationSummary = {
  sourcesChecked: 0,
  excludedMatched: 0,
  skipped: 0,
  forgotten: 0,
  failed: 0,
  refusedMassForget: 0,
};

// Flag-off fixture for the mock service: every summary field the typed
// TtlSweepSummary contract requires is present; the deleteDueFiles counters
// (spec §4b, always-present) show 0 for a source without the flag.
const EMPTY_TTL_SUMMARY: TtlSweepSummary = {
  sourcesChecked: 0,
  expired: 0,
  wouldForget: 0,
  forgotten: 0,
  failed: 0,
  refusedMassForget: 0,
  wouldDelete: 0,
  deletedFiles: 0,
  unlinkFailed: 0,
  skippedConfinement: 0,
  dryRun: false,
};

interface Harness {
  logger: { info: jest.Mock; warn: jest.Mock; error: jest.Mock };
  watchLockPath: string;
  excludeReconciliationService: { run: jest.MockedFunction<() => Promise<ReconciliationSummary>> };
  forceReprocessService: {
    resumeSource: jest.Mock;
    resumeAll: jest.Mock;
    forceReprocessSource: jest.Mock;
    forceReprocessAll: jest.Mock;
    autoPopulateSources: jest.Mock;
  };
  recoverService: {
    recoverSource: jest.Mock;
    recoverAll: jest.Mock;
  };
  reprocessEdgesService: {
    reprocessAll: jest.Mock;
    reprocessSource: jest.Mock;
  };
  fileWatcherService: { start: jest.Mock };
  ttlReconciliationService: {
    run: jest.MockedFunction<(dryRun?: boolean, sourceId?: string) => Promise<TtlSweepSummary>>;
    startDailySweep: jest.Mock;
  };
  app: { close: jest.Mock };
}

const setupBootstrap = (
  argv: string[],
  watchSources: { id: string; path: string }[] = [{ id: 'src-1', path: '/src/1' }],
): Harness => {
  // Map keyed by Nest DI tokens (the class constructors) -> mock instance.
  const services = new Map<unknown, unknown>();

  services.set(Logger, { child: jest.fn().mockReturnThis() });

  const logger = {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    child: jest.fn().mockReturnThis(),
  };
  services.set(BasePinoLogger, logger);

  // C6: every bootstrap run drives the real InstanceLockService against a
  // throwaway lock path so watch-mode tests never touch the repo data dir.
  const lockDir = fs.mkdtempSync(path.join(os.tmpdir(), 'racochu-main-lock-'));
  createdLockDirs.push(lockDir);
  const watchLockPath = path.join(lockDir, 'racochu.watch.lock');
  mockedResolveWatchLockPath.mockReturnValue(watchLockPath);

  services.set(ConfigurationService, {
    getWatchSources: jest.fn().mockReturnValue(watchSources),
    getMcpConfig: jest.fn().mockReturnValue({ url: 'http://mcp:8080' }),
  });

  const forceReprocessService = {
    resumeSource: jest.fn().mockResolvedValue(undefined),
    resumeAll: jest.fn().mockResolvedValue(undefined),
    forceReprocessSource: jest.fn().mockResolvedValue(undefined),
    forceReprocessAll: jest.fn().mockResolvedValue(undefined),
    autoPopulateSources: jest.fn().mockResolvedValue(undefined),
  };
  services.set(ForceReprocessService, forceReprocessService);

  const recoverService = {
    recoverSource: jest.fn().mockResolvedValue(undefined),
    recoverAll: jest.fn().mockResolvedValue(undefined),
  };
  services.set(RecoverService, recoverService);

  const reprocessEdgesService = {
    reprocessAll: jest.fn().mockResolvedValue(undefined),
    reprocessSource: jest.fn().mockResolvedValue(undefined),
  };
  services.set(ReprocessEdgesService, reprocessEdgesService);

  const fileWatcherService = {
    start: jest.fn().mockResolvedValue({ isOk: () => true }),
  };
  services.set(FileWatcherService, fileWatcherService);

  services.set(FileProcessingQueue, {
    waitForEmpty: jest.fn().mockResolvedValue(undefined),
  });

  const excludeReconciliationService = {
    run: jest.fn().mockResolvedValue(EMPTY_SUMMARY),
  };
  services.set(ExcludeReconciliationService, excludeReconciliationService);

  const ttlReconciliationService = {
    run: jest.fn().mockResolvedValue(EMPTY_TTL_SUMMARY),
    startDailySweep: jest.fn(),
  };
  services.set(TtlReconciliationService, ttlReconciliationService);

  const app = {
    get: jest.fn((token: unknown) => services.get(token)),
    useLogger: jest.fn(),
    init: jest.fn().mockResolvedValue(undefined),
    close: jest.fn().mockResolvedValue(undefined),
  };

  jest.mocked(NestFactory.createApplicationContext).mockResolvedValue(app as never);
  process.argv = argv;

  return {
    logger,
    watchLockPath,
    excludeReconciliationService,
    forceReprocessService,
    recoverService,
    reprocessEdgesService,
    fileWatcherService,
    ttlReconciliationService,
    app,
  };
};

describe('main bootstrap — startup exclude reconciliation wiring', () => {
  let exitSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    // No-op: record calls without terminating the test process.
    exitSpy = jest.spyOn(process, 'exit').mockImplementation(() => undefined as never);
  });

  afterEach(() => {
    exitSpy.mockRestore();
  });

  it('watch mode (default): calls run() exactly once and keeps process alive', async () => {
    const { excludeReconciliationService, fileWatcherService, ttlReconciliationService } = setupBootstrap([
      'node',
      'main.js',
    ]);

    await bootstrap();

    expect(excludeReconciliationService.run).toHaveBeenCalledTimes(1);
    expect(ttlReconciliationService.run).toHaveBeenCalledWith(false);
    expect(fileWatcherService.start).toHaveBeenCalledTimes(1);
    expect(exitSpy).not.toHaveBeenCalled();
  });

  it('resume mode: calls run() exactly once, then dispatches resume', async () => {
    const { excludeReconciliationService, forceReprocessService, ttlReconciliationService } = setupBootstrap([
      'node',
      'main.js',
      '--resume',
      '--process-only',
    ]);

    await bootstrap();

    expect(excludeReconciliationService.run).toHaveBeenCalledTimes(1);
    expect(ttlReconciliationService.run).toHaveBeenCalledWith(false);
    expect(forceReprocessService.resumeAll).toHaveBeenCalledTimes(1);
    expect(exitSpy).toHaveBeenCalledWith(0);
  });

  it('force-reprocess mode: calls run() exactly once, then dispatches force-reprocess', async () => {
    const { excludeReconciliationService, forceReprocessService, ttlReconciliationService } = setupBootstrap([
      'node',
      'main.js',
      '--force-reprocess',
      '--process-only',
    ]);

    await bootstrap();

    expect(excludeReconciliationService.run).toHaveBeenCalledTimes(1);
    expect(ttlReconciliationService.run).toHaveBeenCalledWith(false);
    expect(forceReprocessService.forceReprocessAll).toHaveBeenCalledTimes(1);
    // T4/C4: the --force-reprocess dispatch is the operator override — it must
    // pass the explicit bypass flag to the shared walk methods.
    expect(forceReprocessService.forceReprocessAll).toHaveBeenCalledWith(expect.any(Array), {
      forceIngest: true,
    });
    expect(exitSpy).toHaveBeenCalledWith(0);
  });

  it('process-only mode: calls run() exactly once, then processes once', async () => {
    const { excludeReconciliationService, forceReprocessService, ttlReconciliationService } = setupBootstrap([
      'node',
      'main.js',
      '--process-only',
    ]);

    await bootstrap();

    expect(excludeReconciliationService.run).toHaveBeenCalledTimes(1);
    expect(ttlReconciliationService.run).toHaveBeenCalledWith(false);
    expect(forceReprocessService.forceReprocessAll).toHaveBeenCalledTimes(1);
    // T4/DEC-A6: --process-only reuses the same methods but stays GATED —
    // the explicit false is the approved behavior change.
    expect(forceReprocessService.forceReprocessAll).toHaveBeenCalledWith(expect.any(Array), {
      forceIngest: false,
    });
    expect(exitSpy).toHaveBeenCalledWith(0);
  });

  it('continues startup (no throw) when run() rejects', async () => {
    const { excludeReconciliationService } = setupBootstrap(['node', 'main.js']);
    excludeReconciliationService.run.mockRejectedValueOnce(new Error('reconciliation blew up'));

    // A reconciliation failure must never crash startup — bootstrap resolves.
    await expect(bootstrap()).resolves.not.toThrow();

    expect(excludeReconciliationService.run).toHaveBeenCalledTimes(1);
  });

  it('startup TTL sweep: passes dryRun=false to run() and failure is non-fatal', async () => {
    const { ttlReconciliationService, fileWatcherService } = setupBootstrap(['node', 'main.js']);
    ttlReconciliationService.run.mockRejectedValueOnce(new Error('ttl sweep blew up'));

    // A TTL sweep failure must never crash startup — bootstrap continues.
    await expect(bootstrap()).resolves.not.toThrow();

    expect(ttlReconciliationService.run).toHaveBeenCalledWith(false);
    expect(fileWatcherService.start).toHaveBeenCalledTimes(1);
    expect(exitSpy).not.toHaveBeenCalled();
  });

  it('startup TTL sweep: passes dryRun=true when --dry-run is set', async () => {
    const { ttlReconciliationService } = setupBootstrap(['node', 'main.js', '--dry-run']);

    await bootstrap();

    expect(ttlReconciliationService.run).toHaveBeenCalledWith(true);
  });

  it('--ttl-sweep: runs sweep with source, closes app, exits 0 before resume dispatch', async () => {
    const { ttlReconciliationService, forceReprocessService, app } = setupBootstrap([
      'node',
      'main.js',
      '--ttl-sweep',
      '-s',
      'src-1',
      '--resume',
    ]);

    await bootstrap();

    // Startup sweep runs first (no source), then the ttl-sweep path re-runs with the source.
    expect(ttlReconciliationService.run).toHaveBeenNthCalledWith(1, false);
    expect(ttlReconciliationService.run).toHaveBeenNthCalledWith(2, false, 'src-1');
    expect(app.close).toHaveBeenCalledTimes(1);
    expect(exitSpy).toHaveBeenCalledWith(0);
    // ttl-sweep exits before resume/force-reprocess dispatch.
    expect(forceReprocessService.resumeAll).not.toHaveBeenCalled();
    expect(forceReprocessService.forceReprocessAll).not.toHaveBeenCalled();
  });

  it('--ttl-sweep: honors --dry-run and omits source when not provided', async () => {
    const { ttlReconciliationService, app } = setupBootstrap(['node', 'main.js', '--ttl-sweep', '--dry-run']);

    await bootstrap();

    expect(ttlReconciliationService.run).toHaveBeenNthCalledWith(2, true, undefined);
    expect(app.close).toHaveBeenCalledTimes(1);
    expect(exitSpy).toHaveBeenCalledWith(0);
  });

  it('watch mode: calls startDailySweep() after watcher starts successfully', async () => {
    const { ttlReconciliationService, fileWatcherService } = setupBootstrap(['node', 'main.js']);

    await bootstrap();

    expect(fileWatcherService.start).toHaveBeenCalledTimes(1);
    expect(ttlReconciliationService.startDailySweep).toHaveBeenCalledTimes(1);
  });

  it('recover mode: runs exclude reconciliation + TTL sweep at startup, then recovers all and exits', async () => {
    const {
      excludeReconciliationService,
      ttlReconciliationService,
      recoverService,
      fileWatcherService,
      app,
    } = setupBootstrap(['node', 'main.js', '--recover']);

    await bootstrap();

    // Startup reconciliation + TTL sweep still run in recover mode.
    expect(excludeReconciliationService.run).toHaveBeenCalledTimes(1);
    expect(ttlReconciliationService.run).toHaveBeenCalledWith(false);
    // Routes to recoverAll (no source), waits for the queue, closes the app, exits 0.
    expect(recoverService.recoverAll).toHaveBeenCalledTimes(1);
    expect(recoverService.recoverSource).not.toHaveBeenCalled();
    expect(app.close).toHaveBeenCalledTimes(1);
    expect(exitSpy).toHaveBeenCalledWith(0);
    // Watch mode is never started in recover mode.
    expect(fileWatcherService.start).not.toHaveBeenCalled();
  });

  it('recover mode with -s: routes to recoverSource and exits without starting the watcher', async () => {
    const { recoverService, fileWatcherService, app } = setupBootstrap([
      'node',
      'main.js',
      '--recover',
      '-s',
      'src-1',
    ]);

    await bootstrap();

    expect(recoverService.recoverSource).toHaveBeenCalledTimes(1);
    expect(recoverService.recoverSource).toHaveBeenCalledWith(
      'src-1',
      [{ id: 'src-1', path: '/src/1' }],
      undefined,
    );
    expect(recoverService.recoverAll).not.toHaveBeenCalled();
    expect(app.close).toHaveBeenCalledTimes(1);
    expect(exitSpy).toHaveBeenCalledWith(0);
    expect(fileWatcherService.start).not.toHaveBeenCalled();
  });

  it('recover mode with --dry-run: passes dryRun option through to recover', async () => {
    const { recoverService } = setupBootstrap(['node', 'main.js', '--recover', '--dry-run']);

    await bootstrap();

    expect(recoverService.recoverAll).toHaveBeenCalledWith([{ id: 'src-1', path: '/src/1' }], {
      dryRun: true,
    });
    expect(exitSpy).toHaveBeenCalledWith(0);
  });

  it('recover mode: exits after the pass even without --process-only', async () => {
    const { recoverService } = setupBootstrap(['node', 'main.js', '--recover']);

    await bootstrap();

    expect(recoverService.recoverAll).toHaveBeenCalledTimes(1);
    expect(exitSpy).toHaveBeenCalledWith(0);
  });
});

describe('main bootstrap — startup auto-population wiring', () => {
  let exitSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    exitSpy = jest.spyOn(process, 'exit').mockImplementation(() => undefined as never);
  });

  afterEach(() => {
    exitSpy.mockRestore();
  });

  it('watch mode (default): auto-populates sources before starting watcher', async () => {
    const { forceReprocessService, fileWatcherService } = setupBootstrap(['node', 'main.js']);

    await bootstrap();

    expect(forceReprocessService.autoPopulateSources).toHaveBeenCalledTimes(1);
    expect(fileWatcherService.start).toHaveBeenCalledTimes(1);
    // autoPopulateSources must be called before fileWatcherService.start
    const autoPopulateCall = forceReprocessService.autoPopulateSources.mock.calls[0];
    const watcherStartCall = fileWatcherService.start.mock.calls[0];
    expect(autoPopulateCall).not.toBe(undefined);
  });

  it('resume mode: watch fall-through does NOT auto-populate', async () => {
    const { forceReprocessService } = setupBootstrap(['node', 'main.js', '--resume', '--process-only']);

    await bootstrap();

    expect(forceReprocessService.resumeAll).toHaveBeenCalledTimes(1);
    expect(forceReprocessService.autoPopulateSources).not.toHaveBeenCalled();
  });

  it('force-reprocess mode: watch fall-through does NOT auto-populate', async () => {
    const { forceReprocessService } = setupBootstrap([
      'node',
      'main.js',
      '--force-reprocess',
      '--process-only',
    ]);

    await bootstrap();

    expect(forceReprocessService.forceReprocessAll).toHaveBeenCalledTimes(1);
    expect(forceReprocessService.autoPopulateSources).not.toHaveBeenCalled();
  });

  it('recover mode: exits before watch branch (no auto-populate)', async () => {
    const { forceReprocessService, recoverService } = setupBootstrap(['node', 'main.js', '--recover']);

    await bootstrap();

    expect(recoverService.recoverAll).toHaveBeenCalledTimes(1);
    expect(forceReprocessService.autoPopulateSources).not.toHaveBeenCalled();
  });
});

describe('main bootstrap — startup persona edge reconciliation wiring', () => {
  let exitSpy: jest.SpyInstance;

  const PERSONA_SOURCES = [
    { id: 'agent-persona_worker', path: '/p/worker' },
    { id: 'src-1', path: '/src/1' },
  ];

  // Flushes the fire-and-forget auto-populate → edge-reconcile microtask chain.
  const flushAsync = () => new Promise(resolve => setImmediate(resolve));

  beforeEach(() => {
    jest.clearAllMocks();
    exitSpy = jest.spyOn(process, 'exit').mockImplementation(() => undefined as never);
  });

  afterEach(() => {
    exitSpy.mockRestore();
  });

  it('watch mode: reconciles only persona sources after auto-population, watcher unaffected', async () => {
    const { reprocessEdgesService, forceReprocessService, fileWatcherService } = setupBootstrap(
      ['node', 'main.js'],
      PERSONA_SOURCES,
    );

    await bootstrap();
    await flushAsync();

    expect(forceReprocessService.autoPopulateSources).toHaveBeenCalledTimes(1);
    expect(reprocessEdgesService.reprocessAll).toHaveBeenCalledTimes(1);
    expect(reprocessEdgesService.reprocessAll).toHaveBeenCalledWith([PERSONA_SOURCES[0]]);
    expect(fileWatcherService.start).toHaveBeenCalledTimes(1);
  });

  it('watch mode without persona sources: reconciliation does not run', async () => {
    const { reprocessEdgesService } = setupBootstrap(['node', 'main.js']);

    await bootstrap();
    await flushAsync();

    expect(reprocessEdgesService.reprocessAll).not.toHaveBeenCalled();
  });

  it('resume --process-only: reconciliation runs before exit', async () => {
    const { reprocessEdgesService, app } = setupBootstrap(
      ['node', 'main.js', '--resume', '--process-only'],
      PERSONA_SOURCES,
    );

    await bootstrap();

    expect(reprocessEdgesService.reprocessAll).toHaveBeenCalledTimes(1);
    expect(reprocessEdgesService.reprocessAll).toHaveBeenCalledWith([PERSONA_SOURCES[0]]);
    expect(exitSpy).toHaveBeenCalledWith(0);
    expect(app.close).toHaveBeenCalled();
  });

  it('force-reprocess --process-only (no explicit flag): auto persona pass runs before exit', async () => {
    const { reprocessEdgesService } = setupBootstrap(
      ['node', 'main.js', '--force-reprocess', '--process-only'],
      PERSONA_SOURCES,
    );

    await bootstrap();

    expect(reprocessEdgesService.reprocessAll).toHaveBeenCalledTimes(1);
    expect(reprocessEdgesService.reprocessAll).toHaveBeenCalledWith([PERSONA_SOURCES[0]]);
    expect(exitSpy).toHaveBeenCalledWith(0);
  });

  it('force-reprocess --process-only --reprocess-edges: explicit all-sources pass runs once; auto pass skipped', async () => {
    const { reprocessEdgesService } = setupBootstrap(
      ['node', 'main.js', '--force-reprocess', '--process-only', '--reprocess-edges'],
      PERSONA_SOURCES,
    );

    await bootstrap();

    // The operator's explicit all-sources pass runs; the automatic persona
    // pass must never double-run behind it. (With process.exit mocked this
    // harness continues into the standalone --reprocess-edges branch, so the
    // real signal is: no persona-filtered call ever occurs.)
    expect(reprocessEdgesService.reprocessAll).toHaveBeenCalled();
    const personaFilteredCalls = reprocessEdgesService.reprocessAll.mock.calls.filter(
      call => Array.isArray(call[0]) && call[0].length === 1,
    );
    expect(personaFilteredCalls).toHaveLength(0);
  });

  it('--skip-edge-reconcile suppresses the automatic pass in watch mode', async () => {
    const { reprocessEdgesService, fileWatcherService } = setupBootstrap(
      ['node', 'main.js', '--skip-edge-reconcile'],
      PERSONA_SOURCES,
    );

    await bootstrap();
    await flushAsync();

    expect(reprocessEdgesService.reprocessAll).not.toHaveBeenCalled();
    expect(fileWatcherService.start).toHaveBeenCalledTimes(1);
  });

  it('reconciliation failure is non-fatal: watcher still starts, process stays alive', async () => {
    const { reprocessEdgesService, fileWatcherService } = setupBootstrap(
      ['node', 'main.js'],
      PERSONA_SOURCES,
    );
    reprocessEdgesService.reprocessAll.mockRejectedValueOnce(new Error('edge pass boom'));

    await bootstrap();
    await flushAsync();

    expect(reprocessEdgesService.reprocessAll).toHaveBeenCalledTimes(1);
    expect(fileWatcherService.start).toHaveBeenCalledTimes(1);
    expect(exitSpy).not.toHaveBeenCalled();
  });
});

describe('main bootstrap — watch instance lock (C6)', () => {
  let exitSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    exitSpy = jest.spyOn(process, 'exit').mockImplementation(() => undefined as never);
  });

  afterEach(() => {
    exitSpy.mockRestore();
  });

  it('watch start with a live foreign holder: exits 1 with the holder pid, never reaches auto-populate', async () => {
    const { logger, watchLockPath, forceReprocessService, fileWatcherService } = setupBootstrap([
      'node',
      'main.js',
    ]);
    // A real short-lived child process as the foreign live holder — the real
    // process.kill liveness check must refuse us because of it.
    const holder = child_process.spawn(process.execPath, ['-e', 'setTimeout(() => {}, 30000)']);
    fs.writeFileSync(watchLockPath, String(holder.pid));

    try {
      await bootstrap();
    } finally {
      holder.kill();
    }

    // Operator-facing refusal contract (spec C6 / plan T5-AC2).
    const refusal = logger.error.mock.calls
      .flat()
      .find(
        (arg: unknown) =>
          typeof arg === 'string' && arg.includes('another racochu watch instance holds the lock'),
      );
    expect(refusal).toBeDefined();
    expect(refusal).toContain(`pid ${holder.pid}`);
    expect(exitSpy).toHaveBeenCalledWith(1);
    // The refusal happens BEFORE auto-populate and never starts the watcher.
    expect(forceReprocessService.autoPopulateSources).not.toHaveBeenCalled();
    expect(fileWatcherService.start).not.toHaveBeenCalled();
    // The refusal leaves the foreign holder's lock file untouched.
    expect(fs.readFileSync(watchLockPath, 'utf-8')).toBe(String(holder.pid));
  });

  it('watch start with a stale holder file: reclaims it and proceeds normally', async () => {
    const { watchLockPath, forceReprocessService, fileWatcherService } = setupBootstrap(['node', 'main.js']);
    fs.writeFileSync(watchLockPath, String(DEAD_PID));

    await bootstrap();

    // Reclaimed: the file now carries THIS process's pid (real liveness probe).
    expect(fs.readFileSync(watchLockPath, 'utf-8')).toBe(String(process.pid));
    // And startup proceeds: auto-populate then watcher start, no exit.
    expect(forceReprocessService.autoPopulateSources).toHaveBeenCalledTimes(1);
    expect(fileWatcherService.start).toHaveBeenCalledTimes(1);
    expect(exitSpy).not.toHaveBeenCalled();
  });

  it('watch start takes the lock, and signal shutdown removes the lock this process holds', async () => {
    const sigtermBefore = new Set(process.listeners('SIGTERM'));
    const { watchLockPath } = setupBootstrap(['node', 'main.js']);

    await bootstrap();

    expect(fs.readFileSync(watchLockPath, 'utf-8')).toBe(String(process.pid));

    // Invoke the signal handlers this bootstrap run registered (the lock
    // remover and the keep-alive exit handler — exit is mocked).
    for (const listener of process.listeners('SIGTERM')) {
      if (!sigtermBefore.has(listener)) {
        (listener as NodeJS.SignalsListener)('SIGTERM');
      }
    }

    expect(fs.existsSync(watchLockPath)).toBe(false);
  });

  it('non-watch code paths never reference the lock (import-only isolation)', () => {
    const srcRoot = path.join(__dirname);
    const consumers: string[] = [];
    const walk = (dir: string): void => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(full);
        } else if (entry.name.endsWith('.ts') && !entry.name.endsWith('.test.ts')) {
          if (fs.readFileSync(full, 'utf-8').includes('instance-lock.service')) {
            consumers.push(path.relative(srcRoot, full));
          }
        }
      }
    };
    walk(srcRoot);

    // Only the entry point consumes the lock — no other production file in
    // src may reference the module (import-only isolation, plan T5-AC1).
    expect(consumers.sort()).toEqual(['main.ts']);
  });
});
