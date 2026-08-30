import '@/utils/mastra-rag.test-utils';

import { FILE_OPERATIONS } from '@/domain/events/file-events';
import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { ProcessFileUseCase } from '@/use-cases/process-file.use-case';
import { aProcessFileUseCase } from '@/use-cases/process-file.use-case.test-utils';
import { Result } from '@/utils/result';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { Test, TestingModule } from '@nestjs/testing';
import * as chokidar from 'chokidar';
import * as os from 'os';
import * as path from 'path';

import { ConfigurationService } from '../config/configuration.service';
import { aConfigService } from '../config/configuration.service.test-utils';
import { BasePinoLogger } from '../logging/base-pino-logger';
import { aLogger } from '../logging/logger.test-utils';
import { BensyneClient } from './bensyne-client.service';
import { aBensyneClientService } from './bensyne-client.test-utils';
import { FileWatcherService } from './file-watcher.service';

jest.mock('chokidar', () => ({
  watch: jest.fn(),
}));

describe('FileWatcherService', () => {
  let service: FileWatcherService;
  let configService: jest.Mocked<ConfigurationService>;
  let mockLogger: jest.Mocked<BasePinoLogger>;
  let mockBensyneClient: jest.Mocked<BensyneClient>;
  let mockWatcher: jest.Mocked<chokidar.FSWatcher>;
  let mockProcessFileUseCase: ReturnType<typeof aProcessFileUseCase>;
  const mockWatchFn = jest.mocked(chokidar.watch);

  beforeEach(async () => {
    jest.clearAllMocks();

    const mockOnFn = jest.fn((_event, _handler) => mockWatcher);
    mockWatcher = {
      on: mockOnFn,
      close: jest.fn().mockResolvedValue(undefined),
    } as unknown as jest.Mocked<chokidar.FSWatcher>;
    mockWatchFn.mockReturnValue(mockWatcher);

    configService = aConfigService();

    mockLogger = aLogger();

    mockBensyneClient = aBensyneClientService() as unknown as jest.Mocked<BensyneClient>;

    mockProcessFileUseCase = aProcessFileUseCase();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        FileWatcherService,
        { provide: ConfigurationService, useValue: configService },
        { provide: BasePinoLogger, useValue: mockLogger },
        { provide: BensyneClient, useValue: mockBensyneClient },
        { provide: ProcessFileUseCase, useValue: mockProcessFileUseCase },
        EventEmitter2,
      ],
    }).compile();

    service = module.get(FileWatcherService);
  });

  describe('start()', () => {
    it('creates watchers for all configured sources', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'vault', path: '~/vault' }),
        aWatchSourceConfig({ id: 'sessions', path: '~/.agent-sessions' }),
      ];
      configService.getWatchSources.mockReturnValue(sources);

      const result = await service.start();

      expect(result.isOk()).toBe(true);
      expect(mockWatchFn).toHaveBeenCalledTimes(2);
      expect(mockWatchFn).toHaveBeenCalledWith(
        path.join(os.homedir(), 'vault'),
        expect.objectContaining({
          persistent: true,
          ignoreInitial: true,
          awaitWriteFinish: expect.objectContaining({
            stabilityThreshold: 3000,
            pollInterval: 100,
          }),
        }),
      );
      expect(mockWatchFn).toHaveBeenCalledWith(
        path.join(os.homedir(), '.agent-sessions'),
        expect.any(Object),
      );
    });

    it('logs errors when a source fails to start but continues with others', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'source-1', path: '/valid' }),
        aWatchSourceConfig({ id: 'source-2', path: '/valid' }),
      ];
      configService.getWatchSources.mockReturnValue(sources);

      // Simulate failure on second watch call
      mockWatchFn.mockImplementationOnce(() => mockWatcher);
      mockWatchFn.mockImplementationOnce(() => {
        throw new Error('ENOENT');
      });

      const result = await service.start();

      expect(result.isOk()).toBe(true);
    });
  });

  describe('stop()', () => {
    it('closes all watchers', async () => {
      configService.getWatchSources.mockReturnValue([aWatchSourceConfig()]);
      await service.start();

      const result = await service.stop();

      expect(result.isOk()).toBe(true);
      expect(mockWatcher.close).toHaveBeenCalled();
    });

    it('handles errors when closing a watcher without failing', async () => {
      configService.getWatchSources.mockReturnValue([aWatchSourceConfig()]);
      await service.start();

      mockWatcher.close.mockRejectedValueOnce(new Error('watcher error'));

      const result = await service.stop();

      expect(result.isOk()).toBe(true);
    });
  });

  describe('file added event', () => {
    it('delegates file added to ProcessFileUseCase', async () => {
      configService.getWatchSources.mockReturnValue([aWatchSourceConfig()]);
      await service.start();

      const addHandler = mockWatcher.on.mock.calls.find(call => call[0] === 'add')?.[1] as
        ((filePath: string) => void) | undefined;

      addHandler?.('/test/new-file.md');

      expect(mockProcessFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          filePath: '/test/new-file.md',
          eventType: FILE_OPERATIONS.ADD,
        }),
      );
    });
  });

  describe('file changed event', () => {
    it('delegates file changed to ProcessFileUseCase', async () => {
      configService.getWatchSources.mockReturnValue([aWatchSourceConfig()]);
      await service.start();

      const changeHandler = mockWatcher.on.mock.calls.find(call => call[0] === 'change')?.[1] as
        ((filePath: string) => void) | undefined;

      changeHandler?.('/test/changed-file.md');

      expect(mockProcessFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          filePath: '/test/changed-file.md',
          eventType: FILE_OPERATIONS.CHANGE,
        }),
      );
    });
  });

  describe('file deleted event', () => {
    it('delegates file deleted to ProcessFileUseCase', async () => {
      configService.getWatchSources.mockReturnValue([aWatchSourceConfig()]);
      await service.start();

      const unlinkHandler = mockWatcher.on.mock.calls.find(call => call[0] === 'unlink')?.[1] as
        ((filePath: string) => void) | undefined;

      unlinkHandler?.('/test/deleted-file.md');

      expect(mockProcessFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          filePath: '/test/deleted-file.md',
          eventType: FILE_OPERATIONS.DELETE,
        }),
      );
    });
  });

  describe('ready event', () => {
    it('registers a ready handler among the watcher emitter registrations', async () => {
      configService.getWatchSources.mockReturnValue([
        aWatchSourceConfig({ id: 'sessions', path: '~/.agent-sessions' }),
      ]);

      await service.start();

      // ADR-3: chokidar's 'ready' is the observable startup proof that a
      // source is actually being watched; if the handler is never wired, a
      // silently-broken watcher produces no signal at all.
      expect(
        mockWatcher.on.mock.calls.some(call => call[0] === 'ready' && typeof call[1] === 'function'),
      ).toBe(true);
    });

    it('logs the source id and normalized root path when the ready handler is invoked', async () => {
      const source = aWatchSourceConfig({ id: 'sessions', path: '~/.agent-sessions' });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const readyHandler = mockWatcher.on.mock.calls.find(call => call[0] === 'ready')?.[1] as
        (() => void) | undefined;
      expect(readyHandler).toBeDefined();

      readyHandler?.();

      // The log message is the observable contract between the ready event
      // and the source/path it refers to — assert the arguments passed to the
      // log call as wiring verification, never logger calls in isolation.
      const normalizedRoot = path.join(os.homedir(), '.agent-sessions');
      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining(`Watcher ready; source="${source.id}"`),
      );
      expect(mockLogger.info).toHaveBeenCalledWith(expect.stringContaining(`path="${normalizedRoot}"`));
    });
  });

  describe('ignore patterns', () => {
    // chokidar calls this predicate with the FULL absolute path for both
    // files and directories; it must return true to ignore a path.
    const getIgnoredCallback = (): ((candidatePath: string) => boolean) => {
      const watchCall = mockWatchFn.mock.calls[0];
      const options = watchCall?.[1] as Record<string, unknown>;
      return options.ignored as (candidatePath: string) => boolean;
    };

    it('exposes ignored as a predicate function', async () => {
      configService.getWatchSources.mockReturnValue([aWatchSourceConfig()]);

      await service.start();

      expect(typeof getIgnoredCallback()).toBe('function');
    });

    it('ignores config exclude globs matched against full absolute paths', async () => {
      const source = aWatchSourceConfig({
        exclude: ['**/tool-responses/**', '.smart-env/**'],
      });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();

      expect(ignored('/abs/.agent-sessions/26/08/23/x/tool-responses/a.json')).toBe(true);
      // dot: true — dotfile dirs like .smart-env must match
      expect(ignored('/abs/x/.smart-env/f.yaml')).toBe(true);
    });

    it('ignores excluded directories themselves (directory avoidance)', async () => {
      const source = aWatchSourceConfig({
        exclude: ['**/node_modules/**', '**/tool-responses/**'],
      });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();

      // chokidar receives the directory path before recursing; returning
      // true here avoids descending into the excluded directory.
      expect(ignored('/abs/x/node_modules')).toBe(true);
      expect(ignored('/abs/x/node_modules/pkg/index.js')).toBe(true);
      expect(ignored('/abs/x/tool-responses')).toBe(true);
      expect(ignored('/abs/x/tool-responses/a.json')).toBe(true);
    });

    it('ignores default patterns: .git, node_modules, .DS_Store, .env (dot: true)', async () => {
      configService.getWatchSources.mockReturnValue([aWatchSourceConfig()]);

      await service.start();

      const ignored = getIgnoredCallback();

      expect(ignored('/abs/.agent-sessions/.git/FETCH_HEAD')).toBe(true);
      expect(ignored('/abs/x/node_modules/pkg/index.js')).toBe(true);
      expect(ignored('/abs/x/.DS_Store')).toBe(true);
      expect(ignored('/abs/x/.env.local')).toBe(true);
    });

    it('never matches material session files (no false positives)', async () => {
      const source = aWatchSourceConfig({
        exclude: ['**/tool-responses/**', '.smart-env/**'],
      });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();
      const materialPaths = [
        '/abs/.agent-sessions/x/session.md',
        '/abs/.agent-sessions/x/specifications/spec.md',
        '/abs/.agent-sessions/x/materials/notes.txt',
      ];

      for (const materialPath of materialPaths) {
        expect(ignored(materialPath)).toBe(false);
      }
    });

    it('never ignores the watched root itself, even when the root matches an exclude glob', async () => {
      const source = aWatchSourceConfig({ id: 'sessions', path: '~/.agent-sessions', exclude: ['**/.*'] });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();
      const rootPath = path.join(os.homedir(), '.agent-sessions');

      // chokidar calls ignored(root) before watching anything under the root;
      // a dot-named root like ~/.agent-sessions must NOT be excluded by its own
      // '**/.*' exclude, or no events are ever delivered.
      expect(ignored(rootPath)).toBe(false);
    });

    it('normalizes a trailing slash on the root candidate before comparing (root guard)', async () => {
      const source = aWatchSourceConfig({ id: 'sessions', path: '~/.agent-sessions', exclude: ['**/.*'] });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();

      // The guard compares the normalized candidate against the normalized
      // root, so a trailing-slash variant of the root is still not excluded.
      expect(ignored(`${path.join(os.homedir(), '.agent-sessions')}/`)).toBe(false);
    });

    it('uses the normalized root (without a trailing slash) as the chokidar watch path', async () => {
      const source = aWatchSourceConfig({ id: 'sessions', path: '~/.agent-sessions', exclude: ['**/.*'] });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const watchCall = mockWatchFn.mock.calls[0];
      const watchPath = watchCall?.[0] as string;
      expect(watchPath).toBe(path.join(os.homedir(), '.agent-sessions'));
      expect(watchPath.endsWith('/')).toBe(false);
    });

    it('keeps ignoring dot-directories and dotfiles inside a dot-named root', async () => {
      const source = aWatchSourceConfig({
        id: 'sessions',
        path: '~/.agent-sessions',
        exclude: ['**/.*', '**/.opencode/**'],
      });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();
      const rootPath = path.join(os.homedir(), '.agent-sessions');

      // Excluded dot-directories themselves (directory avoidance) and the
      // files under them stay ignored, even though the root is not.
      expect(ignored(path.join(rootPath, '.git'))).toBe(true);
      expect(ignored(path.join(rootPath, '.git/FETCH_HEAD'))).toBe(true);
      expect(ignored(path.join(rootPath, '.opencode/x.json'))).toBe(true);
      expect(ignored(path.join(rootPath, '.smart-env'))).toBe(true);
    });

    it('is a no-op for a non-dot root (root and descendants behaviour preserved)', async () => {
      const source = aWatchSourceConfig({
        id: 'vault',
        path: '~/vault',
        exclude: ['**/.obsidian/**'],
      });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();
      const rootPath = path.join(os.homedir(), 'vault');

      // Root guard: the root itself is never excluded, even for a non-dot root
      // (the predicate normalizes before comparing, so trailing-slash variants
      // of the root also return false).
      expect(ignored(rootPath)).toBe(false);
      expect(ignored(`${rootPath}/`)).toBe(false);

      // Descendant exclusion semantics are unchanged: an excluded descendant
      // (and the excluded directory itself, for avoidance) is still ignored.
      expect(ignored(path.join(rootPath, '.obsidian/workspace.json'))).toBe(true);
      expect(ignored(path.join(rootPath, '.obsidian'))).toBe(true);
    });

    it('unblocks real material files under a dot-named root despite a bare **/.* exclude', async () => {
      const source = aWatchSourceConfig({
        id: 'sessions',
        path: '~/.agent-sessions',
        exclude: ['**/.*'],
      });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();

      // Without the root guard, the dot-named root would be excluded by its own
      // '**/.*' and chokidar would never deliver events under it. The guard unblocks
      // a real material session file.
      expect(ignored(path.join(os.homedir(), '.agent-sessions/26/08/27/x/session.md'))).toBe(false);
    });

    it('never excludes the dot root itself regardless of configured excludes', async () => {
      const rootPath = path.join(os.homedir(), '.agent-sessions');

      for (const exclude of [['**/.*'], ['**/.*', '**/.*/**']]) {
        const source = aWatchSourceConfig({ id: 'sessions', path: '~/.agent-sessions', exclude });
        configService.getWatchSources.mockReturnValue([source]);

        await service.start();

        const ignored = getIgnoredCallback();

        // Every path exactly equal to the root (with and without a trailing
        // slash) is never excluded, no matter which exclude globs are set.
        expect(ignored(rootPath)).toBe(false);
        expect(ignored(`${rootPath}/`)).toBe(false);
      }
    });

    it('keeps ignoring excluded descendants inside a dot-named root', async () => {
      const source = aWatchSourceConfig({
        id: 'sessions',
        path: '~/.agent-sessions',
        exclude: ['**/.obsidian/**', '**/tool-responses/**'],
      });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();
      const rootPath = path.join(os.homedir(), '.agent-sessions');

      // Explicit source excludes + DEFAULT_IGNORE_GLOBS cover all of these
      // descendant categories; the root guard must not weaken them.
      expect(ignored(path.join(rootPath, '.git/FETCH_HEAD'))).toBe(true);
      expect(ignored(path.join(rootPath, '.git'))).toBe(true);
      expect(ignored(path.join(rootPath, '.obsidian/workspace.json'))).toBe(true);
      expect(ignored(path.join(rootPath, '.obsidian'))).toBe(true);
      expect(ignored(path.join(rootPath, '.DS_Store'))).toBe(true);
      expect(ignored(path.join(rootPath, '.env.local'))).toBe(true);
      expect(ignored(path.join(rootPath, 'node_modules/pkg/index.js'))).toBe(true);
      expect(ignored(path.join(rootPath, 'node_modules'))).toBe(true);
      expect(ignored(path.join(rootPath, 'tool-responses/a.json'))).toBe(true);
      expect(ignored(path.join(rootPath, 'tool-responses'))).toBe(true);
    });

    it('never filters material session files under a dot-named root', async () => {
      const source = aWatchSourceConfig({
        id: 'sessions',
        path: '~/.agent-sessions',
        exclude: ['**/.*', '**/.obsidian/**', '**/tool-responses/**'],
      });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const ignored = getIgnoredCallback();
      const rootPath = path.join(os.homedir(), '.agent-sessions');

      const materialPaths = [
        path.join(rootPath, 'session.md'),
        path.join(rootPath, 'specifications/spec.md'),
        path.join(rootPath, 'materials/notes.txt'),
      ];

      for (const materialPath of materialPaths) {
        expect(ignored(materialPath)).toBe(false);
      }
    });
  });

  describe('debounce behavior', () => {
    it('uses awaitWriteFinish with source debounceMs', async () => {
      const source = aWatchSourceConfig({ debounceMs: 5000 });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const watchCall = mockWatchFn.mock.calls[0];
      const options = watchCall?.[1] as Record<string, unknown>;

      expect(options.awaitWriteFinish).toEqual(
        expect.objectContaining({
          stabilityThreshold: 5000,
          pollInterval: 100,
        }),
      );
    });
  });

  describe('onApplicationBootstrap', () => {
    it('calls start and logs error if a source fails to start', async () => {
      configService.getWatchSources.mockReturnValue([aWatchSourceConfig()]);
      mockWatchFn.mockImplementation(() => {
        throw new Error('start failed');
      });

      await service.onApplicationBootstrap();
    });
  });

  describe('onApplicationShutdown', () => {
    it('calls stop', async () => {
      configService.getWatchSources.mockReturnValue([aWatchSourceConfig()]);
      await service.start();

      await service.onApplicationShutdown();

      expect(mockWatcher.close).toHaveBeenCalled();
    });
  });

  describe('memory bank registration', () => {
    it('calls registerBank for sources with description', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'vault', memoryBank: 'vault', description: 'Personal vault notes' }),
        aWatchSourceConfig({ id: 'sessions', memoryBank: 'sessions', description: 'Agent sessions' }),
      ];
      configService.getWatchSources.mockReturnValue(sources);
      mockBensyneClient.registerBank.mockResolvedValue(Result.ok(undefined as unknown as void));

      await service.onApplicationBootstrap();

      expect(mockBensyneClient.registerBank).toHaveBeenCalledTimes(2);
      expect(mockBensyneClient.registerBank).toHaveBeenCalledWith('vault', 'Personal vault notes');
      expect(mockBensyneClient.registerBank).toHaveBeenCalledWith('sessions', 'Agent sessions');
    });

    it('skips sources without description', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'vault', memoryBank: 'vault', description: 'Personal vault notes' }),
        aWatchSourceConfig({ id: 'no-desc', memoryBank: 'no-desc' }),
      ];
      configService.getWatchSources.mockReturnValue(sources);
      mockBensyneClient.registerBank.mockResolvedValue(Result.ok(undefined as unknown as void));

      await service.onApplicationBootstrap();

      expect(mockBensyneClient.registerBank).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.registerBank).toHaveBeenCalledWith('vault', 'Personal vault notes');
    });

    it('logs warning on registration failure and continues with other memory banks', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'vault', memoryBank: 'vault', description: 'Vault' }),
        aWatchSourceConfig({ id: 'sessions', memoryBank: 'sessions', description: 'Sessions' }),
      ];
      configService.getWatchSources.mockReturnValue(sources);

      // First call succeeds, second fails
      mockBensyneClient.registerBank
        .mockResolvedValueOnce(Result.ok(undefined as unknown as void))
        .mockResolvedValueOnce(Result.ko([new Error('connection refused')]));

      await service.onApplicationBootstrap();

      expect(mockBensyneClient.registerBank).toHaveBeenCalledTimes(2);
    });

    it('registers memory banks before starting watchers', async () => {
      const callOrder: string[] = [];

      mockWatchFn.mockImplementation(() => {
        callOrder.push('watch');
        return mockWatcher;
      });

      mockBensyneClient.registerBank.mockImplementation(async () => {
        callOrder.push('registerBank');
        return Result.ok(undefined as unknown as void);
      });

      const sources = [aWatchSourceConfig({ id: 'vault', memoryBank: 'vault', description: 'Vault' })];
      configService.getWatchSources.mockReturnValue(sources);

      await service.onApplicationBootstrap();

      // registerBank must be called before chokidar.watch
      const registerIndex = callOrder.indexOf('registerBank');
      const watchIndex = callOrder.indexOf('watch');
      expect(registerIndex).toBeGreaterThanOrEqual(0);
      expect(watchIndex).toBeGreaterThanOrEqual(0);
      expect(registerIndex).toBeLessThan(watchIndex);
    });

    it('does not block startup when all registrations fail', async () => {
      const sources = [aWatchSourceConfig({ id: 'vault', memoryBank: 'vault', description: 'Vault' })];
      configService.getWatchSources.mockReturnValue(sources);
      mockBensyneClient.registerBank.mockResolvedValue(Result.ko([new Error('MCP error')]));

      await service.onApplicationBootstrap();

      // Watchers still started despite registration failure
      expect(mockWatchFn).toHaveBeenCalled();
    });

    it('does not register when no sources have descriptions', async () => {
      const sources = [aWatchSourceConfig({ id: 'no-desc', memoryBank: 'no-desc' })];
      configService.getWatchSources.mockReturnValue(sources);

      await service.onApplicationBootstrap();

      expect(mockBensyneClient.registerBank).not.toHaveBeenCalled();
    });
  });
});
