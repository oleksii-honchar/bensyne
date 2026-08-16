#!/usr/bin/env node

/**
 * CLI entry point for Racochu.
 * NestJS CLI server — no HTTP controllers; file events drive the system.
 */

import { NestFactory } from '@nestjs/core';
import { Logger } from 'nestjs-pino';
import pino from 'pino';
import 'reflect-metadata';
import { AppModule } from './app.module';
import { ForceReprocessService } from './application/force-reprocess.service';
import { ConfigurationService } from './infrastructure/config/configuration.service';
import { BasePinoLogger } from './infrastructure/logging/base-pino-logger';
import { NestjsPinoLogger } from './infrastructure/logging/nestjs-pino-logger';
import { CliArgsService } from './infrastructure/services/cli-args.service';
import { FileProcessingQueue } from './infrastructure/services/file-processing-queue.service';
import { FileWatcherService } from './infrastructure/services/file-watcher.service';

async function bootstrap(): Promise<void> {
  // Parse CLI args before NestJS bootstrap (need minimal logger for help/version)
  const tempLogger = new NestjsPinoLogger(pino({ level: 'warn' }));
  const args = new CliArgsService(tempLogger).parse(process.argv.slice(2));

  // Handle help and version early
  if (args.help) {
    new CliArgsService(tempLogger).showHelp();
    process.exit(0);
  }

  if (args.version) {
    new CliArgsService(tempLogger).showVersion();
    process.exit(0);
  }

  // Configure bootstrap env vars so AppConfig picks them up at NestJS bootstrap
  if (process.argv.some(a => a === '-c' || a === '--config')) {
    process.env.APP_CONFIG_PATH = args.config;
  }
  process.env.LOG_VERBOSE = String(args.verbose) as 'true' | 'false';

  const loggerLevel: ('log' | 'debug' | 'verbose' | 'warn' | 'error')[] = args.verbose
    ? ['log', 'debug', 'verbose', 'warn', 'error']
    : ['log', 'warn', 'error'];

  const app = await NestFactory.createApplicationContext(AppModule, {
    logger: loggerLevel,
  });

  const nestLogger = app.get(Logger);
  app.useLogger(nestLogger);

  await app.init();

  // Resolve services for CLI-specific startup logic
  const logger = app.get(BasePinoLogger);
  const configurationService = app.get(ConfigurationService);
  const forceReprocessService = app.get(ForceReprocessService);
  const fileWatcherService = app.get(FileWatcherService);
  const processingQueue = app.get(FileProcessingQueue);

  const mode = args.forceReprocess
    ? `force-reprocess${args.source ? ` (${args.source})` : ' (all)'}`
    : args.processOnly
      ? 'process-only'
      : 'watch';
  logger.info(
    `racochu starting: mode="${mode}", verbose=${args.verbose}, config="${args.config}"${args.source ? `, source="${args.source}"` : ''}`,
  );

  const sources = configurationService.getWatchSources();
  logger.info(`Loaded ${sources.length} watch sources`);
  for (const source of sources) {
    logger.info(`  - ${source.id}: ${source.path}`);
  }

  const mcpConfig = configurationService.getMcpConfig();
  logger.info(`MCP endpoint: ${mcpConfig.url}`);

  // Handle force-reprocess
  if (args.forceReprocess) {
    if (args.source) {
      logger.info(`Force reprocessing source: ${args.source}`);
      await forceReprocessService.forceReprocessSource(args.source, sources);
    } else {
      logger.info('Force reprocessing all sources');
      await forceReprocessService.forceReprocessAll(sources);
    }

    // If --process-only with --force-reprocess, wait for queue then exit
    if (args.processOnly) {
      await processingQueue.waitForEmpty();
      logger.info('Force reprocessing complete, exiting');
      await app.close();
      process.exit(0);
    }
  }

  // Handle process-only (no force-reprocess)
  if (args.processOnly && !args.forceReprocess) {
    logger.info('Process-only mode: processing existing files without watching');
    if (args.source) {
      await forceReprocessService.forceReprocessSource(args.source, sources);
    } else {
      await forceReprocessService.forceReprocessAll(sources);
    }
    await processingQueue.waitForEmpty();
    logger.info('Processing complete, exiting');
    await app.close();
    process.exit(0);
  }

  // Start file watcher (default watch mode)
  if (args.watch) {
    logger.info('Starting file watcher');
    const startResult = await fileWatcherService.start();
    if (startResult.isOk()) {
      logger.info('File watcher started. Watching for changes...');
    } else {
      logger.error(`Failed to start file watcher: ${startResult.getFormattedErrors()}`);
    }
  }

  // Keep process alive for watch mode
  // Handle SIGINT/SIGTERM for graceful shutdown
  process.on('SIGINT', async () => {
    console.log('Received SIGINT, shutting down gracefully...');
    await app.close();
    process.exit(0);
  });

  process.on('SIGTERM', async () => {
    console.log('Received SIGTERM, shutting down gracefully...');
    await app.close();
    process.exit(0);
  });
}

bootstrap().catch((error: unknown) => {
  console.error('Failed to start racochu:', error);
  process.exit(1);
});
