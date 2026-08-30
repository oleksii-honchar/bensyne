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

/**
 * Format a Date as an ISO-8601 timestamp in HOST LOCAL time.
 *
 * Unlike `Date.prototype.toISOString()` (always UTC, trailing `Z`), this
 * builds the string from local date components plus the host UTC offset
 * derived from `getTimezoneOffset()`, e.g. `2026-08-23T18:29:05.123+02:00`
 * on a CEST host.
 */
export function formatLocalIsoTimestamp(date: Date): string {
  const pad = (n: number, length = 2): string => String(n).padStart(length, '0');
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const absOffset = Math.abs(offsetMinutes);
  const offset = `${sign}${pad(Math.floor(absOffset / 60))}:${pad(absOffset % 60)}`;

  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `.${pad(date.getMilliseconds(), 3)}${offset}`
  );
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
    timestamp: () => `,"timestamp":"${formatLocalIsoTimestamp(new Date())}"`,
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
      translateTime: 'SYS:yyyy-mm-dd HH:MM:ss',
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
  // symlink=true creates current.log → current active file (pino-roll hardcodes the link name)
  transports.push({
    target: 'pino-roll',
    options: {
      file: LOG_FILE,
      frequency: 'daily', // was period: '1d' (invalid, silently ignored)
      size: '10m', // unchanged — already correct
      limit: {
        count: 3, // was keep: 3 (no such v4 option)
        removeOtherLogFiles: true, // prune legacy racochu.<n>.log files from prior processes
      },
      symlink: true, // was 'racochu.log' string; v4 contract is boolean
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
