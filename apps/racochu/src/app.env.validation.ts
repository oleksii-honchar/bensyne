import { plainToInstance } from 'class-transformer';
import { IsOptional, IsString, validateSync } from 'class-validator';

/**
 * Environment variables schema for Racochu.
 * Mirrors subscriptions-api pattern: class-transformer + class-validator with validateSync.
 *
 * Used by ConfigModule.forRoot({ validate }) at bootstrap to fail fast on invalid env.
 */
export class AppEnvironmentVariables {
  @IsString()
  @IsOptional()
  public APP_CONFIG_PATH!: string;

  @IsString()
  @IsOptional()
  public LOG_VERBOSE!: string;

  @IsString()
  @IsOptional()
  public LOG_LEVEL!: string;

  @IsString()
  @IsOptional()
  public ENV_FILE!: string;

  @IsString()
  @IsOptional()
  public HOME!: string;
}

export function validateAppEnv(config: Record<string, unknown>): AppEnvironmentVariables {
  const validatedConfig = plainToInstance(AppEnvironmentVariables, config, {
    enableImplicitConversion: true,
  });

  const errors = validateSync(validatedConfig, {
    skipMissingProperties: false,
    skipUndefinedProperties: false,
    skipNullProperties: false,
  });

  if (errors.length > 0) {
    const messages = errors.flatMap(err => Object.values(err.constraints ?? {}) as string[]).join(', ');
    throw new Error(`Environment validation failed: ${messages}`);
  }

  return validatedConfig;
}
