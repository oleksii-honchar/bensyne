import { Injectable, Scope } from '@nestjs/common';
import type pino from 'pino';

import { BasePinoLogger } from './base-pino-logger';

@Injectable({ scope: Scope.TRANSIENT })
export class NestjsPinoLogger implements BasePinoLogger {
  constructor(private readonly pinoLogger: pino.Logger) {}

  setContext(_context: string): void {
    // Context is managed via bindings in child loggers
  }

  private buildLogArgs(
    message: string | Record<string, unknown>,
    meta?: Record<string, unknown>,
  ): Record<string, unknown> | string {
    if (meta != null && Object.keys(meta).length > 0) {
      if (typeof message === 'string') {
        return { ...meta, msg: message };
      }
      return { ...meta, ...message };
    }
    return message;
  }

  log(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.info(message, meta);
  }

  info(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.pinoLogger.info(this.buildLogArgs(message, meta));
  }

  error(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.pinoLogger.error(this.buildLogArgs(message, meta));
  }

  warn(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.pinoLogger.warn(this.buildLogArgs(message, meta));
  }

  debug(message: string | Record<string, unknown>, meta?: Record<string, unknown>): void {
    this.pinoLogger.debug(this.buildLogArgs(message, meta));
  }

  child(bindings: Record<string, unknown>): BasePinoLogger {
    const childLogger = this.pinoLogger.child(bindings);
    return new NestjsPinoLogger(childLogger);
  }
}
