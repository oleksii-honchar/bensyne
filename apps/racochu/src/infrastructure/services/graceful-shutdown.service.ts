import { Injectable, OnApplicationShutdown } from '@nestjs/common';
import { BasePinoLogger } from '../logging/base-pino-logger';
import { FileProcessingQueue } from './file-processing-queue.service';
import { FileWatcherService } from './file-watcher.service';
import { BensyneClient } from './bensyne-client.service';

@Injectable()
export class GracefulShutdownService implements OnApplicationShutdown {
  private readonly logger: BasePinoLogger;

  constructor(
    private readonly fileWatcherService: FileWatcherService,
    private readonly processingQueue: FileProcessingQueue,
    private readonly bensyneClient: BensyneClient,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'GracefulShutdownService' });
  }

  /**
   * Safely log during shutdown — falls back to console.log if logger is already closed.
   */
  private safeLog(level: 'info' | 'error' | 'warn', message: string, meta?: Record<string, unknown>): void {
    try {
      const logger = this.logger as BasePinoLogger;
      if (level === 'info') {
        logger.info(message, meta);
      } else if (level === 'error') {
        logger.error(message, meta);
      } else {
        logger.warn(message, meta);
      }
    } catch {
      // Logger already closed during shutdown — fall back to console
      console[level](`[GracefulShutdownService] ${message}`, meta ?? '');
    }
  }

  async onApplicationShutdown(signal?: string): Promise<void> {
    this.safeLog('info', 'Initiating graceful shutdown', { signal });

    try {
      // 1. Stop file watchers first
      this.safeLog('info', 'Stopping file watchers');
      await this.fileWatcherService.stop();
      this.safeLog('info', 'File watchers stopped');

      // 2. Drain processing queue
      this.safeLog('info', 'Draining processing queue');
      // Wait for queue to empty (with timeout)
      await this.waitForQueue();
      this.safeLog('info', 'Processing queue drained');

      // 3. Close MCP client (cleans up SSE connection)
      this.safeLog('info', 'Closing MCP client');
      await this.bensyneClient.close();
      this.safeLog('info', 'MCP client closed');

      this.safeLog('info', 'Graceful shutdown completed');
    } catch (error) {
      this.safeLog('error', 'Error during graceful shutdown', {
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async waitForQueue(): Promise<void> {
    const timeout = 30000; // 30 second timeout
    const startTime = Date.now();

    while (this.processingQueue.length > 0 || this.processingQueue.isProcessing()) {
      if (Date.now() - startTime > timeout) {
        this.safeLog('warn', 'Queue drain timeout reached', {
          remaining: this.processingQueue.length,
        });
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
}
