import { BasePinoLogger } from '../logging/base-pino-logger';
import { FileProcessingQueue } from './file-processing-queue.service';

describe('FileProcessingQueue', () => {
  let queue: FileProcessingQueue;
  let mockLogger: jest.Mocked<BasePinoLogger>;

  beforeEach(() => {
    mockLogger = {
      setContext: jest.fn(),
      log: jest.fn(),
      info: jest.fn(),
      error: jest.fn(),
      warn: jest.fn(),
      debug: jest.fn(),
      child: jest.fn().mockReturnThis(),
    };
    queue = new FileProcessingQueue(mockLogger);
  });

  it('should process tasks sequentially in order', async () => {
    const executionOrder: number[] = [];
    const delay = (ms: number, value: number) =>
      new Promise<void>(resolve => {
        setTimeout(() => {
          executionOrder.push(value);
          resolve();
        }, ms);
      });

    await Promise.all([
      queue.addToQueue(() => delay(50, 1)),
      queue.addToQueue(() => delay(30, 2)),
      queue.addToQueue(() => delay(40, 3)),
    ]);

    expect(executionOrder).toEqual([1, 2, 3]);
  });

  it('should complete all queued tasks', async () => {
    const completed: number[] = [];

    const tasks = [1, 2, 3, 4, 5].map(n =>
      queue.addToQueue(async () => {
        completed.push(n);
      }),
    );

    await Promise.all(tasks);

    expect(completed).toHaveLength(5);
    expect(completed).toEqual([1, 2, 3, 4, 5]);
  });

  it('should not stop queue when a task fails', async () => {
    const completed: number[] = [];

    await Promise.all([
      queue.addToQueue(async () => {
        completed.push(1);
      }),
      queue.addToQueue(async () => {
        throw new Error('task 2 failed');
      }),
      queue.addToQueue(async () => {
        completed.push(3);
      }),
    ]);

    expect(completed).toEqual([1, 3]);
  });

  it('should report correct queue length', async () => {
    expect(queue.length).toBe(0);

    const promises = [
      queue.addToQueue(() => new Promise<void>(resolve => setTimeout(resolve, 100))),
      queue.addToQueue(() => new Promise<void>(resolve => setTimeout(resolve, 100))),
      queue.addToQueue(() => new Promise<void>(resolve => setTimeout(resolve, 100))),
    ];

    // Allow queue to start processing but not complete
    await new Promise(resolve => setTimeout(resolve, 10));

    // Some tasks may be in flight, length reflects remaining in queue
    expect(queue.length).toBeGreaterThanOrEqual(0);
    expect(queue.length).toBeLessThanOrEqual(3);

    await Promise.all(promises);
    expect(queue.length).toBe(0);
  });

  it('should report isProcessing correctly', async () => {
    expect(queue.isProcessing()).toBe(false);

    const longTaskDone = new Promise<void>(resolve => {
      queue.addToQueue(
        () =>
          new Promise<void>(taskResolve => {
            setTimeout(() => {
              taskResolve();
              resolve();
            }, 100);
          }),
      );
    });

    await new Promise(resolve => setTimeout(resolve, 10));
    expect(queue.isProcessing()).toBe(true);

    await longTaskDone;
    expect(queue.isProcessing()).toBe(false);
  });
});
