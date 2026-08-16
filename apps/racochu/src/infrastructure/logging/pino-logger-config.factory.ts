import { ConfigService } from '@nestjs/config';
import * as fs from 'fs';
import type { Params } from 'nestjs-pino';
import * as os from 'os';
import * as path from 'path';

import pkg from '../../../package.json';

const LOG_DIR = path.join(os.homedir(), '.local', 'share', 'racochu', 'logs');
const LOG_FILE = path.join(LOG_DIR, 'racochu.log');

function ensureLogDir(): void {
  if (!fs.existsSync(LOG_DIR)) {
    fs.mkdirSync(LOG_DIR, { recursive: true });
  }
}

export function pinoLoggerConfigFactory(configService: ConfigService): Params {
  const serviceName = pkg.name;

  const environment = configService.get<string>('nodeEnv') ?? process.env.NODE_ENV ?? 'development';

  const logLevel = configService.get<string>('logging.level') ?? process.env.LOG_LEVEL ?? 'info';

  const verboseFromConfig = configService.get<boolean | string>('logging.verbose');

  const isLocalLogVerbose =
    verboseFromConfig === true ||
    String(verboseFromConfig).toLowerCase() === 'true' ||
    process.env.VERBOSE?.toLowerCase() === 'true';

  ensureLogDir();

  const pinoHttpOptions: {
    level: string;
    messageKey: string;
    timestamp: () => string;
    base: Record<string, unknown>;
    transport?: {
      targets: { target: string; options: Record<string, unknown>; level?: string }[];
    };
  } = {
    level: isLocalLogVerbose ? 'debug' : logLevel,
    messageKey: 'msg',
    timestamp: () => `,"timestamp":"${new Date(Date.now()).toISOString()}"`,
    base: {
      environment,
      service: serviceName,
    },
  };

  const transports: { target: string; options: Record<string, unknown>; level?: string }[] = [];

  // Console transport: pretty-printed for terminal
  transports.push({
    target: 'pino-pretty',
    options: {
      colorize: true,
      autoLogging: false,
      messageKey: 'message',
      translateTime: 'yyyy-mm-dd HH:MM:ss',
      singleLine: false,
      ignore: 'pid,hostname',
      ...(isLocalLogVerbose
        ? {}
        : {
            messageFormat: '{if component}[{component}] {end}{msg}',
            include: 'level,name,time',
          }),
    },
  });

  // File transport: JSON, line-delimited, with rotation
  // symlink=true creates racochu.log → current active file
  transports.push({
    target: 'pino-roll',
    options: {
      file: LOG_FILE,
      period: '1d',
      size: '10m',
      keep: 3,
      symlink: 'racochu.log',
      sync: false,
      mkdir: true,
    },
    level: logLevel,
  });

  pinoHttpOptions.transport = { targets: transports };

  return {
    pinoHttp: pinoHttpOptions as Params['pinoHttp'],
  };
}
