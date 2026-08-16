/**
 * Base use case class with observability support.
 * Follows DDD rules for use case structure and error handling.
 * Simplified for Racochu — no DEFAULT_PROPERTIES_TO_LOG complexity.
 */

import { Result } from './result';

export interface BasePinoLogger {
  info(message: string, metadata?: Record<string, unknown>): void;
  error(message: string, metadata?: Record<string, unknown>): void;
  debug(message: string, metadata?: Record<string, unknown>): void;
  warn(message: string, metadata?: Record<string, unknown>): void;
  child(bindings: Record<string, unknown>): BasePinoLogger;
}

export abstract class BaseUseCase<TParams, TResult> {
  public logger: BasePinoLogger;

  constructor(logger: BasePinoLogger) {
    this.logger = logger;
    this.logger = this.logger.child({ useCase: this.constructor.name });
  }

  /**
   * Validates and optionally transforms params before execution.
   * Override this to add validation (e.g. zod parse); do not override execute().
   * @default returns Result.ok(params)
   */
  protected validateParams(params: TParams): Result<TParams> {
    return Result.ok(params);
  }

  /**
   * Entry point for the use case. Must not be overridden.
   * Override validateParams() for validation and executeInternal() for business logic.
   */
  async execute(params: TParams): Promise<Result<TResult>> {
    const requestName = this.constructor.name;
    this.logger = this.logger.child({ useCase: requestName });

    const validated = this.validateParams(params);
    if (validated.isKo()) {
      const metadata = {
        action: requestName,
        error: validated.getErrors(),
      };
      this.logger.error(`[use-case] Validation failed: ${requestName}`, metadata);
      return Result.ko(validated.getErrors()) as Result<TResult>;
    }
    const validParams = validated.getValue();

    const defaultMetadata: Record<string, string> = {
      action: requestName,
    };

    this.logger.debug(`[use-case] Processing: ${requestName}`, defaultMetadata);

    return await this.executeInternal(validParams);
  }

  protected abstract executeInternal(params: TParams): Promise<Result<TResult>>;
}
