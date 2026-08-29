import { Injectable } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { WatchSourceConfig } from '../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { FileProcessingQueue } from '../infrastructure/services/file-processing-queue.service';
import { ProcessFileUseCase } from '../use-cases/process-file.use-case';
import { isPathExcluded } from './glob-matcher';

@Injectable()
export class ForceReprocessService {
  private readonly logger: BasePinoLogger;

  constructor(
    private readonly processFileUseCase: ProcessFileUseCase,
    private readonly processingQueue: FileProcessingQueue,
    private readonly fileMemoryTrackerService: FileMemoryTrackerService,
    private readonly bensyneClient: BensyneClient,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'ForceReprocessService' });
  }

  async forceReprocessAll(sources: WatchSourceConfig[]): Promise<void> {
    this.logger.info(`Force reprocessing all sources: count=${sources.length}`);

    for (const source of sources) {
      await this.processSource(source);
    }
  }

  async forceReprocessSource(sourceId: string, sources: WatchSourceConfig[]): Promise<void> {
    this.logger.info(`Force reprocessing source; id="${sourceId}"`);

    const source = sources.find(s => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      return;
    }

    await this.processSource(source);
  }

  async resumeAll(sources: WatchSourceConfig[]): Promise<void> {
    this.logger.info(`Resuming missing chunks for all sources: count=${sources.length}`);

    for (const source of sources) {
      await this.resumeSourceInternal(source);
    }
  }

  async resumeSource(sourceId: string, sources: WatchSourceConfig[]): Promise<void> {
    this.logger.info(`Resuming missing chunks for source; id="${sourceId}"`);

    const source = sources.find(s => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      return;
    }

    await this.resumeSourceInternal(source);
  }

  private async resumeSourceInternal(source: WatchSourceConfig): Promise<void> {
    try {
      const files = await this.getFiles(source);
      this.logger.info(
        `Files found for resume: source="${source.id}", path="${source.path}", count=${files.length}`,
      );

      // [i/totalFilesInQueue] is the 1-based queue position (not a stored index).
      const totalFilesInQueue = files.length;
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const position = i + 1;

        let memoryIds: string[];
        try {
          memoryIds = await this.fileMemoryTrackerService.getMemoryIds(file);
        } catch (error) {
          this.logger.warn(
            `Skipping file for resume; failed to read stored memory count [${position}/${totalFilesInQueue}]: path="${file}", error="${error instanceof Error ? error.message : String(error)}"`,
          );
          continue;
        }

        // Bank-verified skip: the tracker can be stale (e.g. bank wiped) — a
        // file with tracked memories is verified against the bank before being
        // trusted as complete (mirrors RecoverService.recoverFile).
        if (memoryIds.length > 0) {
          const chunksResult = await this.bensyneClient.getFileChunks(file, source.memoryBank);
          if (chunksResult.isKo()) {
            // Bank read failed (MCP down / error). Skip defensively — never
            // re-ingest on a transient failure (duplicate-memory risk);
            // --recover remains the guaranteed reconciliation tool.
            this.logger.warn(
              `Bank read error for resume [${position}/${totalFilesInQueue}]: path="${file}", error="${chunksResult.getFormattedErrors()}" — skipping (preserving existing memories)`,
            );
            continue;
          }

          const fileChunks = chunksResult.getValue();

          if (fileChunks.status !== 'FILE_NOT_FOUND' && fileChunks.chunks.length > 0) {
            this.logger.debug(
              `Skipping verified file for resume [${position}/${totalFilesInQueue}]: path="${file}", memories="${memoryIds.length}"`,
            );
            continue;
          }

          this.logger.info(
            `Resuming stale-tracker file (absent from bank) [${position}/${totalFilesInQueue}]: path="${file}"`,
          );
        } else {
          this.logger.info(`Resuming untracked file [${position}/${totalFilesInQueue}]: path="${file}"`);
        }

        const result = await this.processFileUseCase.execute({
          filePath: file,
          eventType: 'add',
          sourceId: source.id,
          memoryBank: source.memoryBank,
          sourceConfig: source,
        });

        if (result.isKo()) {
          this.logger.error(`File resume failed: path="${file}", error="${result.getFormattedErrors()}"`);
        }
      }
    } catch (error) {
      this.logger.error(
        `Failed to resume source: id="${source.id}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }
  }

  private async processSource(source: WatchSourceConfig): Promise<void> {
    try {
      const files = await this.getFiles(source);
      this.logger.info(
        `Files found for reprocessing: source="${source.id}", path="${source.path}", count=${files.length}`,
      );

      // Execute directly — execute() → executeInternal() → addToQueue() already
      // serializes via the queue. Awaiting keeps processing strictly sequential.
      // [i/totalFilesInQueue] is the 1-based queue position (not a stored index).
      const totalFilesInQueue = files.length;
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const position = i + 1;

        this.logger.info(`Processing file [${position}/${totalFilesInQueue}]: path="${file}"`);

        const result = await this.processFileUseCase.execute({
          filePath: file,
          eventType: 'add',
          sourceId: source.id,
          memoryBank: source.memoryBank,
          sourceConfig: source,
        });

        if (result.isKo()) {
          this.logger.error(
            `File reprocessing failed [${position}/${totalFilesInQueue}]: path="${file}", error="${result.getFormattedErrors()}"`,
          );
        }
      }
    } catch (error) {
      this.logger.error(
        `Failed to process source: id="${source.id}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }
  }

  private async getFiles(source: WatchSourceConfig): Promise<string[]> {
    const resolvedPath = this.resolvePath(source.path);

    try {
      const stats = await fs.stat(resolvedPath);
      if (!stats.isDirectory()) {
        this.logger.warn(`Source path is not a directory; "${resolvedPath}"`);
        return [];
      }

      return this.scanDirectory(resolvedPath, source);
    } catch (error) {
      this.logger.error(
        `Failed to stat source path: "${resolvedPath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
      return [];
    }
  }

  private async scanDirectory(dirPath: string, source: WatchSourceConfig): Promise<string[]> {
    const files: string[] = [];

    try {
      const entries = await fs.readdir(dirPath, { withFileTypes: true });
      const sourceRoot = this.resolvePath(source.path);

      for (const entry of entries) {
        const fullPath = path.join(dirPath, entry.name);
        const relPath = path.relative(sourceRoot, fullPath);

        if (entry.isDirectory()) {
          // Skip excluded directories using the shared glob matcher.
          if (isPathExcluded(relPath, source.exclude)) {
            continue;
          }
          const subFiles = await this.scanDirectory(fullPath, source);
          files.push(...subFiles);
        } else if (entry.isFile()) {
          if (!isPathExcluded(relPath, source.exclude)) {
            files.push(fullPath);
          }
        }
      }
    } catch (error) {
      this.logger.warn(
        `Failed to read directory: "${dirPath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    return files;
  }

  private resolvePath(filePath: string): string {
    if (filePath.startsWith('~')) {
      return path.join(os.homedir(), filePath.slice(1));
    }
    return path.resolve(filePath);
  }
}
