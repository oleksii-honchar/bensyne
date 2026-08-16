import { LoggerService } from '@nestjs/common';

/**
 * Abstract base class for Pino Logger implementations.
 * Defines the interface that concrete logger implementations must provide.
 */
export abstract class BasePinoLogger implements LoggerService {
  abstract setContext(context: string): void;

  abstract log(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void;

  abstract info(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void;

  abstract error(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void;

  abstract warn(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void;

  abstract debug(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void;

  abstract child(bindings: Record<string, unknown>): BasePinoLogger;
}
