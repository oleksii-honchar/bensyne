import { Injectable } from '@nestjs/common';
import { BasePinoLogger } from '../logging/base-pino-logger';

@Injectable()
export class FileProcessingQueue {
  private readonly logger: BasePinoLogger;
  private queue: {
    task: () => Promise<void>;
    resolve: () => void;
  }[] = [];
  private processing = false;

  constructor(logger: BasePinoLogger) {
    this.logger = logger.child({ component: 'FileProcessingQueue' });
  }

  async addToQueue(task: () => Promise<void>): Promise<void> {
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
          await item.task();
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
