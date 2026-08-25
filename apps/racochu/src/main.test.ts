import { NestFactory } from '@nestjs/core';
import { Logger } from 'nestjs-pino';
import {
  ExcludeReconciliationService,
  ReconciliationSummary,
} from './application/exclude-reconciliation.service';
import { ForceReprocessService } from './application/force-reprocess.service';
import { TtlReconciliationService, TtlSweepSummary } from './application/ttl-reconciliation.service';
import { ConfigurationService } from './infrastructure/config/configuration.service';
import { BasePinoLogger } from './infrastructure/logging/base-pino-logger';
import { FileProcessingQueue } from './infrastructure/services/file-processing-queue.service';
import { FileWatcherService } from './infrastructure/services/file-watcher.service';
import { bootstrap } from './main';

// Mock NestFactory so bootstrap() never constructs a real Nest application.
jest.mock('@nestjs/core', () => ({
  NestFactory: {
    createApplicationContext: jest.fn(),
  },
}));

const EMPTY_SUMMARY: ReconciliationSummary = {
  sourcesChecked: 0,
  excludedMatched: 0,
  skipped: 0,
  forgotten: 0,
  failed: 0,
  refusedMassForget: 0,
};

const EMPTY_TTL_SUMMARY: TtlSweepSummary = {
  sourcesChecked: 0,
  expired: 0,
  wouldForget: 0,
  forgotten: 0,
  failed: 0,
  refusedMassForget: 0,
  dryRun: false,
};

interface Harness {
  excludeReconciliationService: { run: jest.MockedFunction<() => Promise<ReconciliationSummary>> };
  forceReprocessService: {
    resumeSource: jest.Mock;
    resumeAll: jest.Mock;
    forceReprocessSource: jest.Mock;
    forceReprocessAll: jest.Mock;
  };
  fileWatcherService: { start: jest.Mock };
  ttlReconciliationService: {
    run: jest.MockedFunction<(dryRun?: boolean, sourceId?: string) => Promise<TtlSweepSummary>>;
    startDailySweep: jest.Mock;
  };
  app: { close: jest.Mock };
}

const setupBootstrap = (argv: string[]): Harness => {
  // Map keyed by Nest DI tokens (the class constructors) -> mock instance.
  const services = new Map<unknown, unknown>();

  services.set(Logger, { child: jest.fn().mockReturnThis() });

  services.set(BasePinoLogger, {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    child: jest.fn().mockReturnThis(),
  });

  services.set(ConfigurationService, {
    getWatchSources: jest.fn().mockReturnValue([{ id: 'src-1', path: '/src/1' }]),
    getMcpConfig: jest.fn().mockReturnValue({ url: 'http://mcp:8080' }),
  });

  const forceReprocessService = {
    resumeSource: jest.fn().mockResolvedValue(undefined),
    resumeAll: jest.fn().mockResolvedValue(undefined),
    forceReprocessSource: jest.fn().mockResolvedValue(undefined),
    forceReprocessAll: jest.fn().mockResolvedValue(undefined),
  };
  services.set(ForceReprocessService, forceReprocessService);

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

  return { excludeReconciliationService, forceReprocessService, fileWatcherService, ttlReconciliationService, app };
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
});
