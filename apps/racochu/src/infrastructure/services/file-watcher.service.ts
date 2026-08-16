import { CHOKIDAR_EVENTS, FILE_OPERATIONS } from '@/domain/events/file-events';
import { ProcessFileUseCase } from '@/use-cases/process-file.use-case';
import { ErrorWithDetails } from '@/utils/error-with-details';
import { Result } from '@/utils/result';
import { Injectable, OnApplicationBootstrap, OnApplicationShutdown } from '@nestjs/common';
import * as chokidar from 'chokidar';
import { EventEmitter } from 'node:events';
import * as os from 'os';
import * as path from 'path';
import { WatchSourceConfig } from '../config/config-schemas';
import { ConfigurationService } from '../config/configuration.service';
import { BasePinoLogger } from '../logging/base-pino-logger';
import { BensyneClient } from './bensyne-client.service';

@Injectable()
export class FileWatcherService implements OnApplicationBootstrap, OnApplicationShutdown {
  private readonly logger: BasePinoLogger;
  private watchers = new Map<string, { watcher: chokidar.FSWatcher; sourceId: string; sourcePath: string }>();

  constructor(
    private readonly configService: ConfigurationService,
    private readonly processFileUseCase: ProcessFileUseCase,
    private readonly bensyneClient: BensyneClient,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'FileWatcherService' });
  }

  async onApplicationBootstrap(): Promise<void> {
    this.logger.info(`Starting file watcher service: sources=${this.configService.getWatchSources().length}`);

    // Ensure MCP client is initialized before registering memory banks
    const initResult = await this.bensyneClient.initialize();
    if (!initResult.isOk()) {
      this.logger.warn(
        `MCP init failed, memory bank registration may fail: ${initResult.getFormattedErrors()}`,
      );
    }

    await this.registerBanks();
    const result = await this.start();
    if (result.isKo()) {
      this.logger.error(`Failed to start file watcher: ${result.getFormattedErrors()}`);
    }
  }

  private async registerBanks(): Promise<void> {
    const sources = this.configService.getWatchSources();
    const withDescription = sources.filter(s => s.description != null && s.description.length > 0);
    this.logger.info(
      `Registering memory banks: totalSources=${sources.length}, withDescription=${withDescription.length}`,
    );

    for (const source of withDescription) {
      const result = await this.bensyneClient.registerBank(source.memoryBank, source.description!);
      if (result.isOk()) {
        this.logger.info(
          `Memory bank registered: id="${source.id}", memoryBank="${source.memoryBank}", description="${source.description}"`,
        );
      } else {
        this.logger.warn(
          `Failed to register memory bank: id="${source.id}", memoryBank="${source.memoryBank}", error="${result.getFormattedErrors()}"`,
        );
      }
    }
  }

  async start(): Promise<Result<void>> {
    const sources = this.configService.getWatchSources();
    this.logger.info(`Loading watch sources: count=${sources.length}`);

    for (const source of sources) {
      const startResult = await this.startWatchingSource(source);
      if (startResult.isKo()) {
        this.logger.error(
          `Failed to start watching source: id="${source.id}", error="${startResult.getFormattedErrors()}"`,
        );
      }
    }

    this.logger.info(`File watcher started: activeWatchers=${this.watchers.size}`);
    return Result.ok(undefined as unknown as void);
  }

  async stop(): Promise<Result<void>> {
    for (const entry of Array.from(this.watchers.entries())) {
      const [sourceId, { watcher, sourcePath }] = entry;
      try {
        await watcher.close();
        this.logger.info(`Stopped watching source; id="${sourceId}", path="${sourcePath}"`);
      } catch (error) {
        this.logger.error(
          `Error stopping watcher: id="${sourceId}", error="${error instanceof Error ? error.message : String(error)}"`,
        );
      }
    }
    this.watchers.clear();
    return Result.ok(undefined as unknown as void);
  }

  async onApplicationShutdown(): Promise<void> {
    await this.stop();
  }

  private async startWatchingSource(source: WatchSourceConfig): Promise<Result<void>> {
    const resolvedPath = this.resolvePath(source.path);
    this.logger.info(`Watching source; id="${source.id}", path="${resolvedPath}"`);

    let watcher: chokidar.FSWatcher;
    try {
      watcher = chokidar.watch(resolvedPath, {
        ignored: this.buildIgnorePatterns(source),
        persistent: true,
        ignoreInitial: true,
        awaitWriteFinish: {
          stabilityThreshold: source.debounceMs,
          pollInterval: 100,
        },
      });
    } catch (error: unknown) {
      const err = error instanceof Error ? error.message : String(error);
      this.logger.error(
        `Failed to start watcher: source="${source.id}", path="${resolvedPath}", error="${err}"`,
      );
      return Result.ko([new (ErrorWithDetails || Error)(err)]);
    }

    const emitter = watcher as unknown as EventEmitter;
    emitter.on(CHOKIDAR_EVENTS.ADD, (filePath: string) => this.handleFileAdded(filePath, source));
    emitter.on(CHOKIDAR_EVENTS.CHANGE, (filePath: string) => this.handleFileChanged(filePath, source));
    emitter.on(CHOKIDAR_EVENTS.UNLINK, (filePath: string) => this.handleFileDeleted(filePath, source));
    emitter.on('error', (error: unknown) => {
      this.logger.error(
        `Watcher error: source="${source.id}", path="${resolvedPath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    });

    this.watchers.set(source.id, { watcher, sourceId: source.id, sourcePath: resolvedPath });
    return Result.ok(undefined as unknown as void);
  }

  private handleFileAdded(filePath: string, source: WatchSourceConfig): void {
    this.logger.debug(`File added; path="${filePath}", source="${source.id}"`);
    void this.processFileUseCase.execute({
      filePath,
      eventType: FILE_OPERATIONS.ADD,
      sourceId: source.id,
      memoryBank: source.memoryBank,
      sourceConfig: source,
    });
  }

  private handleFileChanged(filePath: string, source: WatchSourceConfig): void {
    this.logger.debug(`File changed; path="${filePath}", source="${source.id}"`);
    void this.processFileUseCase.execute({
      filePath,
      eventType: FILE_OPERATIONS.CHANGE,
      sourceId: source.id,
      memoryBank: source.memoryBank,
      sourceConfig: source,
    });
  }

  private handleFileDeleted(filePath: string, source: WatchSourceConfig): void {
    this.logger.debug(`File deleted; path="${filePath}", source="${source.id}"`);
    void this.processFileUseCase.execute({
      filePath,
      eventType: FILE_OPERATIONS.DELETE,
      sourceId: source.id,
      memoryBank: source.memoryBank,
      sourceConfig: source,
    });
  }

  private resolvePath(filePath: string): string {
    if (filePath.startsWith('~')) {
      return path.join(os.homedir(), filePath.slice(1));
    }
    return path.resolve(filePath);
  }

  private buildIgnorePatterns(source: WatchSourceConfig): (string | RegExp)[] {
    return [
      ...source.exclude,
      '.git/**',
      '**/.git/**',
      'node_modules/**',
      '**/node_modules/**',
      '**/.DS_Store',
      '**/Thumbs.db',
      '**/.env*',
    ];
  }
}
