import { BasePinoLogger, BaseUseCase } from './base-use-case';
import { Result } from './result';

class MockLogger implements BasePinoLogger {
  public logs: { level: string; message: string; metadata?: Record<string, unknown> }[] = [];
  private _bindings: Record<string, unknown> = {};

  constructor(
    private readonly parentLogs?: {
      level: string;
      message: string;
      metadata?: Record<string, unknown>;
    }[],
  ) {}

  info(message: string, metadata?: Record<string, unknown>): void {
    this.logs.push({ level: 'info', message, metadata });
    this.parentLogs?.push({ level: 'info', message, metadata });
  }

  error(message: string, metadata?: Record<string, unknown>): void {
    this.logs.push({ level: 'error', message, metadata });
    this.parentLogs?.push({ level: 'error', message, metadata });
  }

  debug(message: string, metadata?: Record<string, unknown>): void {
    this.logs.push({ level: 'debug', message, metadata });
    this.parentLogs?.push({ level: 'debug', message, metadata });
  }

  warn(message: string, metadata?: Record<string, unknown>): void {
    this.logs.push({ level: 'warn', message, metadata });
    this.parentLogs?.push({ level: 'warn', message, metadata });
  }

  child(bindings: Record<string, unknown>): BasePinoLogger {
    const child = new MockLogger(this.parentLogs ?? this.logs);
    (child as unknown as Record<string, unknown>).__bindings = { ...this._bindings, ...bindings };
    return child;
  }
}

class TestUseCase extends BaseUseCase<{ id: string }, string> {
  protected async executeInternal(params: { id: string }): Promise<Result<string>> {
    return Result.ok(`processed-${params.id}`);
  }
}

class FailingValidationUseCase extends BaseUseCase<{ id: string }, string> {
  protected validateParams(params: { id: string }): Result<{ id: string }> {
    if (!params.id) {
      return Result.ko([new Error('id is required')]);
    }
    return Result.ok(params);
  }

  protected async executeInternal(params: { id: string }): Promise<Result<string>> {
    return Result.ok(`processed-${params.id}`);
  }
}

describe('BaseUseCase', () => {
  describe('constructor', () => {
    it('should set logger with useCase name', () => {
      const logger = new MockLogger();
      const useCase = new TestUseCase(logger);

      expect(useCase.logger).toBeDefined();
      expect(useCase.logger).not.toBe(logger);
      const childLogger = useCase.logger as unknown as Record<string, unknown>;
      expect(childLogger.__bindings).toEqual({ useCase: 'TestUseCase' });
    });
  });

  describe('execute', () => {
    it('should call validateParams then executeInternal when valid', async () => {
      const logger = new MockLogger();
      const useCase = new TestUseCase(logger);

      const result = await useCase.execute({ id: 'test-123' });

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toBe('processed-test-123');
    });

    it('should log debug message when processing', async () => {
      const logger = new MockLogger();
      const useCase = new TestUseCase(logger);

      await useCase.execute({ id: 'test-123' });

      const debugLogs = logger.logs.filter(l => l.level === 'debug');
      expect(debugLogs.length).toBeGreaterThan(0);
      expect(debugLogs[0].message).toContain('[use-case] Processing: TestUseCase');
    });

    it('should return validation error when validateParams fails', async () => {
      const logger = new MockLogger();
      const useCase = new FailingValidationUseCase(logger);

      const result = await useCase.execute({ id: '' });

      expect(result.isKo()).toBe(true);
      expect(result.getErrors()[0].message).toBe('id is required');
    });

    it('should log error when validation fails', async () => {
      const logger = new MockLogger();
      const useCase = new FailingValidationUseCase(logger);

      await useCase.execute({ id: '' });

      const errorLogs = logger.logs.filter(l => l.level === 'error');
      expect(errorLogs.length).toBeGreaterThan(0);
      expect(errorLogs[0].message).toContain('[use-case] Validation failed: FailingValidationUseCase');
      expect(errorLogs[0].metadata).toEqual(
        expect.objectContaining({
          action: 'FailingValidationUseCase',
        }),
      );
      const errorMetadata = errorLogs[0].metadata as Record<string, unknown>;
      expect(Array.isArray(errorMetadata.error)).toBe(true);
      const errors = errorMetadata.error as { message: string }[];
      expect(errors[0].message).toBe('id is required');
    });

    it('should not call executeInternal when validation fails', async () => {
      const logger = new MockLogger();
      const useCase = new FailingValidationUseCase(logger);

      const spy = jest.spyOn(
        FailingValidationUseCase.prototype as unknown as Record<string, unknown>,
        'executeInternal' as never,
      );

      await useCase.execute({ id: '' });

      expect(spy).not.toHaveBeenCalled();
      spy.mockRestore();
    });
  });

  describe('validateParams default', () => {
    it('should return Result.ok(params) by default', () => {
      const logger = new MockLogger();
      const useCase = new TestUseCase(logger);

      const result = (
        useCase as unknown as { validateParams(params: { id: string }): Result<{ id: string }> }
      ).validateParams({ id: 'test' });

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual({ id: 'test' });
    });
  });
});
