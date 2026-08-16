import { registerAs } from '@nestjs/config';
import * as os from 'os';
import * as path from 'path';

/**
 * Application bootstrap configuration sourced from validated environment variables.
 *
 * Usage:
 *   const config = app.get<AppConfig>(AppConfig.KEY);
 *
 * This replaces direct process.env access in configuration.module.ts and cli-args.service.ts.
 */
export const AppConfig = registerAs('app', () => {
  const envAppConfigPath = process.env.APP_CONFIG_PATH;
  const envLogVerbose = process.env.LOG_VERBOSE;
  const envFile = process.env.ENV_FILE;

  return {
    appConfigPath: envAppConfigPath ?? path.join(os.homedir(), '.config', 'racochu.yaml'),
    logVerbose: envLogVerbose === 'true' || envLogVerbose === '1',
    envFile: envFile ?? '.env',
  };
});

export type AppConfig = ReturnType<typeof AppConfig>;
