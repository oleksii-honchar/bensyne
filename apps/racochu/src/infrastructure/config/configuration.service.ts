import { Inject, Injectable, OnApplicationBootstrap } from '@nestjs/common';
import * as chokidar from 'chokidar';
import * as fsSync from 'fs';
import * as fs from 'fs/promises';
import * as yaml from 'js-yaml';
import * as path from 'path';
import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';
import { BasePinoLogger } from '../logging/base-pino-logger';
import {
  ChunkingConfig,
  Configuration,
  configurationSchema,
  EnhancementConfig,
  EnrichmentConfig,
  McpConfig,
  TelemetryConfig,
  WatchSourceConfig,
} from './config-schemas';
import { SOURCE_STRATEGIES } from './source-strategies';

// Matches $VAR_NAME or $VAR_NAME patterns (alphanumeric + underscore, must start with letter/underscore)
const ENV_VAR_PATTERN = /\$([A-Za-z_][A-Za-z0-9_]*)/g;

/**
 * Recursively substitutes $ENV_VAR references in string values with process.env values.
 * Only string values are processed; objects and arrays are recursed into.
 * If an env var is not set, the original $VAR_NAME is left as-is.
 */
export function resolveEnvVars(obj: unknown): unknown {
  if (typeof obj === 'string') {
    return obj.replace(ENV_VAR_PATTERN, (match, varName) => {
      const envValue = process.env[varName];
      return envValue !== undefined ? envValue : match;
    });
  }
  if (Array.isArray(obj)) {
    return obj.map(resolveEnvVars);
  }
  if (obj !== null && typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      result[key] = resolveEnvVars(value);
    }
    return result;
  }
  return obj;
}

export const DEFAULT_CONFIG: Configuration = {
  watchSources: [
    {
      id: 'agent-sessions',
      path: '~/.agent-sessions',
      memoryBank: 'agent-sessions',
      exclude: ['archive/**', '**/archive/**', '.smart-env/**'],
      debounceMs: 5000,
      strategy: SOURCE_STRATEGIES.CONTENT_AWARE,
    },
  ],
  chunking: {
    strategy: SOURCE_STRATEGIES.CONTENT_AWARE,
    maxSizes: {
      agentSessions: 400,
      obsidianNotes: 500,
      codeFiles: 400,
      configuration: 'per-key',
      plainText: 450,
    },
    overlap: 50,
    hardCap: 600,
  },
  enrichment: {
    enabled: false,
    llmUrl: undefined,
    llmModel: undefined,
    apiKey: undefined,
    maxConcurrency: 1,
    timeoutMs: 15000,
    docMaxTokens: 16000,
  },
  enhancement: {
    maxCharacters: {
      prose: 200,
      code: 400,
      configuration: 300,
      documentation: 300,
    },
    importance: {
      enabled: true,
      defaultScore: 0.5,
      factors: [
        { name: 'fileRole', weight: 0.4 },
        { name: 'length', weight: 0.2 },
        { name: 'keywords', weight: 0.3 },
        { name: 'header', weight: 0.1 },
      ],
    },
    tags: {
      enabled: true,
      maxTags: 10,
    },
    source: {
      includePath: true,
      includeSection: true,
      includeMetadata: false,
    },
  },
  mcp: {
    url: 'https://lite-llm.lan/mcp/mnemosyne',
    apiKey: undefined,
    timeoutMs: 30000,
    maxRetries: 3,
    retryDelayMs: 1000,
  },
  telemetry: {
    enabled: true,
    endpoint: 'clickstack-otel-collector:4317',
    service: 'racochu',
    metrics: {
      chunking: true,
      ingestion: true,
      errors: true,
    },
  },
};

@Injectable()
export class ConfigurationService implements OnApplicationBootstrap {
  private readonly logger: BasePinoLogger;
  private config: Configuration | null = null;
  private watcher: chokidar.FSWatcher | null = null;

  constructor(
    logger: BasePinoLogger,
    @Inject('CONFIG_FILE_PATH') private readonly configFilePath: string,
  ) {
    this.logger = logger.child({ component: 'ConfigurationService', configPath: this.configFilePath });
  }

  async load(): Promise<Result<Configuration>> {
    try {
      const content = await fs.readFile(this.configFilePath, 'utf-8');
      const parsed = yaml.load(content) as unknown;
      // Resolve $ENV_VAR references in string values
      const resolved = resolveEnvVars(parsed);

      if (!resolved || typeof resolved !== 'object') {
        return Result.ko([
          new ErrorWithDetails('YAML parsing failed: invalid configuration format', 'ConfigParseError'),
        ]);
      }

      const result = configurationSchema.safeParse(resolved);

      if (!result.success) {
        const errors = result.error.issues
          .map(issue => `${issue.path.join('.')}: ${issue.message}`)
          .join(', ');
        return Result.ko([
          new ErrorWithDetails(`Configuration validation failed: ${errors}`, 'ConfigValidationError'),
        ]);
      }

      this.config = result.data;
      this.logger.info(
        `Configuration loaded: path="${this.configFilePath}", watchSources=${this.config.watchSources.length}`,
      );

      return Result.ok(this.config);
    } catch (error) {
      if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'ENOENT') {
        return Result.ko([
          new ErrorWithDetails(
            `Configuration file not found: ${this.configFilePath}. Run with --init to create default config.`,
            'ConfigFileNotFound',
            { configPath: this.configFilePath },
          ),
        ]);
      }
      return Result.ko([
        new ErrorWithDetails(`Failed to load configuration: ${(error as Error).message}`, 'ConfigLoadError'),
      ]);
    }
  }

  getWatchSources(): WatchSourceConfig[] {
    return this.config?.watchSources ?? [];
  }

  getChunkingConfig(): ChunkingConfig {
    return this.config?.chunking ?? DEFAULT_CONFIG.chunking;
  }

  getEnrichmentConfig(): EnrichmentConfig {
    return this.config?.enrichment ?? DEFAULT_CONFIG.enrichment;
  }

  getMcpConfig(): McpConfig {
    return this.config?.mcp ?? DEFAULT_CONFIG.mcp;
  }

  getTelemetryConfig(): TelemetryConfig {
    return this.config?.telemetry ?? DEFAULT_CONFIG.telemetry;
  }

  getEnhancementConfig(): EnhancementConfig {
    return this.config?.enhancement ?? DEFAULT_CONFIG.enhancement;
  }

  async initializeDefaultConfig(): Promise<Result<void>> {
    try {
      const dir = path.dirname(this.configFilePath);
      await fs.mkdir(dir, { recursive: true });

      const yamlContent = yaml.dump(DEFAULT_CONFIG, {
        indent: 2,
        noRefs: true,
        lineWidth: 120,
      });

      const header = `# ~/.config/racochu.yaml
# Default configuration file - copy and customize as needed
#
# Documentation: https://github.com/oleksii-honchar/racochu

`;

      await fs.writeFile(this.configFilePath, header + yamlContent);

      this.logger.info(`Default configuration created; path="${this.configFilePath}"`);

      return Result.ok(undefined);
    } catch (error) {
      return Result.ko([
        new ErrorWithDetails(
          `Configuration validation failed: ${(error as Error).message}`,
          'ConfigValidationError',
        ),
      ]);
    }
  }

  async onApplicationBootstrap(): Promise<void> {
    // Load configuration
    const loadResult = await this.load();

    if (loadResult.isKo()) {
      const err = loadResult.getErrors()[0];
      if (err.code === 'ConfigFileNotFound') {
        this.logger.info(`Creating default configuration at ${this.configFilePath}...`);
        const initResult = await this.initializeDefaultConfig();
        if (initResult.isOk()) {
          this.config = DEFAULT_CONFIG;
          this.logger.info('Default configuration created and loaded.');
        } else {
          this.logger.warn(
            `Failed to create config file: ${initResult.getFormattedErrors()}. Using in-memory defaults.`,
          );
          this.config = DEFAULT_CONFIG;
        }
      } else {
        this.logger.warn(`Configuration load failed, using defaults: ${err.message}`);
        this.config = DEFAULT_CONFIG;
      }
    }

    // Watch config file for changes (hot-reload)
    this.startConfigWatcher();
  }

  private startConfigWatcher(): void {
    try {
      if (!fsSync.existsSync(this.configFilePath)) {
        this.logger.debug('Config file does not exist, skipping watcher setup');
        return;
      }

      this.watcher = chokidar.watch(this.configFilePath, {
        ignoreInitial: true,
      });

      let reloadTimeout: NodeJS.Timeout | null = null;

      this.watcher.on('change', () => {
        if (reloadTimeout) {
          clearTimeout(reloadTimeout);
        }

        reloadTimeout = setTimeout(async () => {
          this.logger.debug('Config file changed, reloading...');
          const result = await this.load();

          if (result.isKo()) {
            this.logger.error(
              `Config reload failed: ${result.getFormattedErrors()}. Keeping current config.`,
            );
          } else {
            this.logger.info('Configuration reloaded successfully');
          }
        }, 2000);
      });

      this.watcher.on('error', (error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        this.logger.error(`Config watcher error: ${message}`);
      });
    } catch (error) {
      this.logger.warn(`Failed to start config watcher: ${(error as Error).message}`);
    }
  }

  async stop(): Promise<void> {
    if (this.watcher) {
      await this.watcher.close();
      this.watcher = null;
    }
  }
}
