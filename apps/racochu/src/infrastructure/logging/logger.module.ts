import { DynamicModule, Global, Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { LoggerModule as PinoLoggerModule } from 'nestjs-pino';
import pino from 'pino';

import { BasePinoLogger } from './base-pino-logger';
import { NestjsPinoLogger } from './nestjs-pino-logger';
import { pinoLoggerConfigFactory } from './pino-logger-config.factory';

@Global()
@Module({})
export class LoggerModule {
  static forRootAsync(): DynamicModule {
    return {
      module: LoggerModule,
      imports: [
        PinoLoggerModule.forRootAsync({
          inject: [ConfigService],
          useFactory: pinoLoggerConfigFactory,
        }),
      ],
      providers: [
        {
          provide: BasePinoLogger,
          useFactory: (configService: ConfigService) => {
            // Get the same pinoHttp config that LoggerModule uses
            const params = pinoLoggerConfigFactory(configService);
            const pinoHttpConfig = params.pinoHttp as Record<string, unknown>;

            const level = String(pinoHttpConfig?.level ?? 'info');
            const environment = configService.get<string>('nodeEnv') ?? process.env.NODE_ENV ?? 'development';
            const base = {
              ...(pinoHttpConfig?.base ?? {}),
              service: 'racochu',
              environment,
            };

            // Production: include transport config
            const logger = pino({
              level,
              base,
              transport: pinoHttpConfig?.transport as pino.TransportMultiOptions | undefined,
            });
            return new NestjsPinoLogger(logger);
          },
          inject: [ConfigService],
        },
      ],
      exports: [BasePinoLogger],
    };
  }
}
