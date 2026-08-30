import { ConfigModule } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';

import { LoggerModule, PINO_LOGGER } from './logger.module';

/**
 * Regression test: exactly ONE pino instance may exist per process.
 *
 * Each pino instance's `transport` spawns a worker thread; two workers with a
 * pino-roll target race on the `current.log` symlink at startup (EEXIST crash)
 * and double-write every log line. The trap: `ConfigurationModule` imports
 * `LoggerModule` as a plain module — a decorator-level PINO_LOGGER provider
 * would be instantiated in BOTH module instances.
 */
jest.mock('pino', () => {
  // Preserve pino's named exports (pino-http destructures symbols from it)
  // while intercepting the default call to count instantiations.
  // eslint-disable-next-line @typescript-eslint/no-unsafe-return
  const actual = jest.requireActual('pino');
  const state = { count: 0 };
  const fakeLogger = {
    level: 'info',
    messageKey: 'msg',
    base: {},
    info: () => undefined,
    error: () => undefined,
    warn: () => undefined,
    debug: () => undefined,
    trace: () => undefined,
    fatal: () => undefined,
    child: () => fakeLogger,
  };
  const factory = (..._args: unknown[]) => {
    state.count += 1;
    return fakeLogger;
  };
  Object.assign(factory, actual);
  (factory as { __pinoCallCount?: () => number }).__pinoCallCount = () => state.count;
  (factory as { __pinoResetCount?: () => void }).__pinoResetCount = () => {
    state.count = 0;
  };
  return { ...actual, __esModule: true, default: factory };
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const pinoMock = (jest.requireMock('pino') as { default: unknown } & Record<string, unknown>)
  .default as unknown as { __pinoCallCount: () => number; __pinoResetCount: () => void };

describe('LoggerModule pino singleton', () => {
  let module: TestingModule;

  beforeEach(() => {
    pinoMock.__pinoResetCount();
  });

  afterEach(async () => {
    await module?.close();
  });

  it('creates exactly one pino instance even when LoggerModule is imported both dynamically and plainly', async () => {
    module = await Test.createTestingModule({
      // Mirrors AppModule's graph: LoggerModule.forRootAsync() (dynamic) AND
      // the plain LoggerModule import (as ConfigurationModule does) → two
      // module instances of the same class.
      imports: [
        ConfigModule.forRoot({ isGlobal: true }),
        LoggerModule.forRootAsync(),
        LoggerModule,
      ],
      providers: [],
    }).compile();

    await module.init();

    const shared = module.get(PINO_LOGGER, { strict: false });
    expect(shared).toBeDefined();
    // The plain-import instance must NOT have contributed a second pino().
    expect(pinoMock.__pinoCallCount()).toBe(1);
  });
});
