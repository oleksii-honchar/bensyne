import { ConfigModule } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';

import { BasePinoLogger } from './base-pino-logger';
import { LoggerModule } from './logger.module';
import { NestjsPinoLogger } from './nestjs-pino-logger';

describe('LoggingModule', () => {
  let module: TestingModule;
  let logger: BasePinoLogger;

  beforeEach(async () => {
    module = await Test.createTestingModule({
      imports: [ConfigModule.forRoot({ isGlobal: true }), LoggerModule.forRootAsync()],
    }).compile();

    logger = await module.resolve<BasePinoLogger>(BasePinoLogger);
  });

  afterEach(async () => {
    await module?.close();
  });

  it('should be defined', () => {
    expect(LoggerModule).toBeDefined();
  });

  it('should provide BasePinoLogger as NestjsPinoLogger', () => {
    expect(logger).toBeDefined();
    expect(logger).toBeInstanceOf(NestjsPinoLogger);
  });

  it('should have info method', () => {
    expect(typeof logger.info).toBe('function');
  });

  it('should have error method', () => {
    expect(typeof logger.error).toBe('function');
  });

  it('should have warn method', () => {
    expect(typeof logger.warn).toBe('function');
  });

  it('should have debug method', () => {
    expect(typeof logger.debug).toBe('function');
  });

  it('should have child method', () => {
    expect(typeof logger.child).toBe('function');
  });

  it('should have setContext method', () => {
    expect(typeof logger.setContext).toBe('function');
  });

  it('child should return a BasePinoLogger instance', () => {
    const child = logger.child({ requestId: 'test-123' });
    expect(child).toBeDefined();
    expect(child).toBeInstanceOf(NestjsPinoLogger);
  });
});
