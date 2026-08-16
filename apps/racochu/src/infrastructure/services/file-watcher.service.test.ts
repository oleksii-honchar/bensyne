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

  describe('ignore patterns', () => {
    it('applies ignore patterns correctly including defaults', async () => {
      const source = aWatchSourceConfig({
        exclude: ['**/node_modules/**', '**/temp/**'],
      });
      configService.getWatchSources.mockReturnValue([source]);

      await service.start();

      const watchCall = mockWatchFn.mock.calls[0];
      const options = watchCall?.[1] as Record<string, unknown>;
      const ignored = options.ignored as (string | RegExp)[];

      expect(Array.isArray(ignored)).toBe(true);
      expect(ignored).toContain('**/node_modules/**');
      expect(ignored).toContain('**/temp/**');
      expect(ignored).toContain('**/.DS_Store');
      expect(ignored).toContain('**/Thumbs.db');
      expect(ignored).toContain('**/.env*');
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
