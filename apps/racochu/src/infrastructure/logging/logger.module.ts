import { DynamicModule, Global, Module, Provider } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { LoggerModule as PinoLoggerModule } from 'nestjs-pino';
import type { Params } from 'nestjs-pino';
import pino from 'pino';

import { BasePinoLogger } from './base-pino-logger';
import { NestjsPinoLogger } from './nestjs-pino-logger';
import { pinoLoggerConfigFactory } from './pino-logger-config.factory';

/**
 * Injection token for the single shared pino instance.
 *
 * Exactly ONE pino logger must exist per process: its `transport` spawns a
 * worker thread per instance, and two workers with a pino-roll file target
 * race on the `current.log` symlink at startup (EEXIST crash) and double-write
 * every log line afterwards.
 */
export const PINO_LOGGER = 'PINO_LOGGER';

const pinoLoggerProvider: Provider = {
  provide: PINO_LOGGER,
  useFactory: (configService: ConfigService): pino.Logger => {
    const params = pinoLoggerConfigFactory(configService);
    const pinoHttpConfig = params.pinoHttp as Record<string, unknown>;
    return pino({
      level: String(pinoHttpConfig?.level ?? 'info'),
      messageKey: String(pinoHttpConfig?.messageKey ?? 'msg'),
      timestamp: pinoHttpConfig?.timestamp as pino.TimeFn,
      base: pinoHttpConfig?.base as Record<string, unknown>,
      transport: pinoHttpConfig?.transport as pino.TransportMultiOptions | undefined,
    });
  },
  inject: [ConfigService],
};

const basePinoLoggerProvider: Provider = {
  provide: BasePinoLogger,
  useFactory: (pinoLogger: pino.Logger) => new NestjsPinoLogger(pinoLogger),
  inject: [PINO_LOGGER],
};

/**
 * Owns the shared pino instance. A plain (non-dynamic) module class: Nest
 * dedupes it to ONE instance no matter how many modules import it, so the
 * factory runs exactly once per process.
 */
@Module({
  providers: [pinoLoggerProvider],
  exports: [pinoLoggerProvider],
})
export class PinoLoggerProviderModule {}

@Global()
@Module({})
export class LoggerModule {
  static forRootAsync(): DynamicModule {
    return {
      module: LoggerModule,
      imports: [
        PinoLoggerProviderModule,
        // Pass the shared pino instance to nestjs-pino so its Logger/PinoLogger
        // providers and the HTTP middleware reuse it instead of building a
        // second transport (second pino-roll worker → startup race).
        PinoLoggerModule.forRootAsync({
          imports: [PinoLoggerProviderModule],
          inject: [PINO_LOGGER],
          useFactory: (pinoLogger: pino.Logger): Params => ({
            pinoHttp: { logger: pinoLogger },
          }),
        }),
      ],
      providers: [basePinoLoggerProvider],
      exports: [BasePinoLogger],
    };
  }
}
