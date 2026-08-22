import { Injectable } from '@nestjs/common';
import { AsyncLocalStorage } from 'node:async_hooks';
import { BasePinoLogger } from '../logging/base-pino-logger';

@Injectable()
export class FileProcessingQueue {
  private readonly logger: BasePinoLogger;
  private readonly inTaskStorage = new AsyncLocalStorage<boolean>();
  private queue: {
    task: () => Promise<void>;
    resolve: () => void;
  }[] = [];
  private processing = false;

  constructor(logger: BasePinoLogger) {
    this.logger = logger.child({ component: 'FileProcessingQueue' });
  }

  async addToQueue(task: () => Promise<void>): Promise<void> {
    if (this.inTaskStorage.getStore() === true) {
      throw new Error(
        'FileProcessingQueue.addToQueue called from inside a running queued task — this deadlocks the queue. Call it from outside the worker.',
      );
    }
    return new Promise<void>(resolve => {
      this.queue.push({ task, resolve });
      this.processQueue();
    });
  }

  private async processQueue(): Promise<void> {
    if (this.processing || this.queue.length === 0) return;

    this.processing = true;
    try {
      while (this.queue.length > 0) {
        const item = this.queue.shift();
        if (!item) continue;

        try {
          await this.inTaskStorage.run(true, () => item.task());
        } catch (error) {
          this.logger.error(
            `Task failed in processing queue: ${error instanceof Error ? error.message : String(error)}`,
          );
        } finally {
          item.resolve();
        }
      }
    } finally {
      this.processing = false;
    }
  }

  get length(): number {
    return this.queue.length;
  }

  isProcessing(): boolean {
    return this.processing;
  }

  async waitForEmpty(): Promise<void> {
    while (this.queue.length > 0 || this.processing) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
}
