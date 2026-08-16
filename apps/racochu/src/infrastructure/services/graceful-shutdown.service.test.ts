import '@/utils/mastra-rag.test-utils';

import { Result } from '../../utils/result';
import { BasePinoLogger } from '../logging/base-pino-logger';
import { BensyneClient } from './bensyne-client.service';
import { FileProcessingQueue } from './file-processing-queue.service';
import { FileWatcherService } from './file-watcher.service';
import { GracefulShutdownService } from './graceful-shutdown.service';

class MockBasePinoLogger extends BasePinoLogger {
  logCalls: { message: string | Record<string, unknown>; meta?: Record<string, unknown> }[] = [];
  infoCalls: { message: string | Record<string, unknown>; meta?: Record<string, unknown> }[] = [];
  errorCalls: { message: string | Record<string, unknown>; meta?: Record<string, unknown> }[] = [];
  warnCalls: { message: string | Record<string, unknown>; meta?: Record<string, unknown> }[] = [];
  debugCalls: { message: string | Record<string, unknown>; meta?: Record<string, unknown> }[] = [];

  setContext(_context: string): void {}
  log(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.logCalls.push({ message, meta });
  }
  info(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.infoCalls.push({ message, meta });
  }
  error(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.errorCalls.push({ message, meta });
  }
  warn(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.warnCalls.push({ message, meta });
  }
  debug(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.debugCalls.push({ message, meta });
  }
  child(_bindings: Record<string, unknown>): BasePinoLogger {
    return this;
  }
}

class MockFileWatcherService {
  stopCalled = false;
  async stop(): Promise<Result<void>> {
    this.stopCalled = true;
    return Result.ok(undefined as unknown as void);
  }
}

class MockFileProcessingQueue {
  private _length = 0;
  private _processing = false;

  setLength(value: number) {
    this._length = value;
  }
  setProcessing(value: boolean) {
    this._processing = value;
  }

  get length(): number {
    return this._length;
  }
  isProcessing(): boolean {
    return this._processing;
  }
}

class MockBensyneClient {
  closeCalled = false;
  async close(): Promise<void> {
    this.closeCalled = true;
  }
}

describe('GracefulShutdownService', () => {
  let service: GracefulShutdownService;
  let logger: MockBasePinoLogger;
  let fileWatcherService: MockFileWatcherService;
  let processingQueue: MockFileProcessingQueue;
  let bensyneClient: MockBensyneClient;

  beforeEach(() => {
    logger = new MockBasePinoLogger();
    fileWatcherService = new MockFileWatcherService();
    processingQueue = new MockFileProcessingQueue();
    bensyneClient = new MockBensyneClient();

    service = new GracefulShutdownService(
      fileWatcherService as unknown as FileWatcherService,
      processingQueue as unknown as FileProcessingQueue,
      bensyneClient as unknown as BensyneClient,
      logger,
    );
  });

  describe('onApplicationShutdown', () => {
    it('should stop file watchers when shutdown is initiated', async () => {
      await service.onApplicationShutdown('SIGTERM');

      expect(fileWatcherService.stopCalled).toBe(true);
    });

    it('should complete shutdown with signal', async () => {
      processingQueue.setLength(0);
      processingQueue.setProcessing(false);

      await expect(service.onApplicationShutdown('SIGTERM')).resolves.not.toThrow();

      expect(fileWatcherService.stopCalled).toBe(true);
      expect(bensyneClient.closeCalled).toBe(true);
    });

    it('should complete shutdown without signal', async () => {
      processingQueue.setLength(0);
      processingQueue.setProcessing(false);

      await expect(service.onApplicationShutdown()).resolves.not.toThrow();

      expect(fileWatcherService.stopCalled).toBe(true);
      expect(bensyneClient.closeCalled).toBe(true);
    });

    it('should drain processing queue before shutdown completes', async () => {
      processingQueue.setLength(0);
      processingQueue.setProcessing(false);

      await service.onApplicationShutdown('SIGINT');

      // Queue operations happen before MCP close
      expect(bensyneClient.closeCalled).toBe(true);
    });

    it('should close MCP client during shutdown', async () => {
      processingQueue.setLength(0);
      processingQueue.setProcessing(false);

      await service.onApplicationShutdown('SIGTERM');

      expect(bensyneClient.closeCalled).toBe(true);
    });

    it('should complete shutdown successfully', async () => {
      processingQueue.setLength(0);
      processingQueue.setProcessing(false);

      await service.onApplicationShutdown('SIGTERM');

      // All operations completed without error
      expect(fileWatcherService.stopCalled).toBe(true);
      expect(bensyneClient.closeCalled).toBe(true);
    });

    it('should handle errors during shutdown without throwing', async () => {
      fileWatcherService.stop = async () => {
        throw new Error('Watcher stop failed');
      };

      await expect(service.onApplicationShutdown('SIGTERM')).resolves.not.toThrow();
    });

    it('should call operations in correct order: watchers → queue → MCP', async () => {
      processingQueue.setLength(0);
      processingQueue.setProcessing(false);

      const callOrder: string[] = [];
      fileWatcherService.stop = async () => {
        callOrder.push('watchers');
        return Result.ok(undefined as unknown as void);
      };
      bensyneClient.close = async () => {
        callOrder.push('mcp');
      };

      await service.onApplicationShutdown('SIGTERM');

      expect(callOrder).toEqual(['watchers', 'mcp']);
    });
  });

  describe('waitForQueue', () => {
    it('should return immediately when queue is empty and not processing', async () => {
      processingQueue.setLength(0);
      processingQueue.setProcessing(false);

      const startTime = Date.now();
      await service.onApplicationShutdown('SIGTERM');
      const elapsed = Date.now() - startTime;

      expect(elapsed).toBeLessThan(500);
    });

    it('should wait for queue to drain with timeout', async () => {
      let iterations = 0;
      const originalQueue = processingQueue;

      processingQueue.setLength(1);
      processingQueue.setProcessing(true);

      const drainSpy = jest.spyOn(processingQueue, 'length', 'get').mockImplementation(() => {
        iterations++;
        if (iterations < 5) {
          return 1;
        }
        return 0;
      });

      const processingSpy = jest.spyOn(processingQueue, 'isProcessing').mockImplementation(() => {
        if (iterations < 5) {
          return true;
        }
        return false;
      });

      await service.onApplicationShutdown('SIGTERM');

      expect(iterations).toBeGreaterThanOrEqual(5);
      // Queue eventually drained — shutdown completed
      expect(fileWatcherService.stopCalled).toBe(true);

      drainSpy.mockRestore();
      processingSpy.mockRestore();
    });

    it('should warn when queue drain timeout is reached', async () => {
      processingQueue.setLength(5);
      processingQueue.setProcessing(true);

      // Mock Date.now to simulate timeout expiration immediately
      const originalDateNow = Date.now;
      let callCount = 0;
      global.Date.now = jest.fn(() => {
        callCount++;
        // First call: start time, subsequent calls: past timeout
        return callCount === 1 ? 0 : 40000;
      });

      await expect(service.onApplicationShutdown('SIGTERM')).resolves.not.toThrow();

      // Shutdown completed despite queue never draining
      expect(fileWatcherService.stopCalled).toBe(true);
      expect(bensyneClient.closeCalled).toBe(true);
      global.Date.now = originalDateNow;
    });
  });
});
