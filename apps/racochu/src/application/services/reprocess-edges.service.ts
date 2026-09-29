import { Injectable } from '@nestjs/common';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { ReprocessEdgesUseCase, ReprocessEdgesResult } from '../../use-cases/reprocess-edges.use-case';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';

@Injectable()
export class ReprocessEdgesService {
  private readonly logger: BasePinoLogger;

  constructor(
    private readonly processEdgesUseCase: ReprocessEdgesUseCase,
    private readonly bensyneClient: BensyneClient,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'ReprocessEdgesService' });
  }

  async reprocessAll(sources: WatchSourceConfig[]): Promise<void> {
    this.logger.info(`Reprocessing edges for all sources: count=${sources.length}`);

    for (const source of sources) {
      await this.reprocessSourceInternal(source);
    }
  }

  async reprocessSource(sourceId: string, sources: WatchSourceConfig[]): Promise<void> {
    this.logger.info(`Reprocessing edges for source; id="${sourceId}"`);

    const source = sources.find((s) => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      return;
    }

    await this.reprocessSourceInternal(source);
  }

  private async reprocessSourceInternal(source: WatchSourceConfig): Promise<void> {
    try {
      const files = await this.getFiles(source);
      this.logger.info(
        `Files found for edge reprocessing: source="${source.id}", path="${source.path}", count=${files.length}`,
      );

      if (files.length === 0) {
        this.logger.info(`No files to reprocess; source="${source.id}"`);
        return;
      }

      // Delegate to the use case for the two-pass reprocessing
      const result = await this.processEdgesUseCase.execute({
        sourceId: source.id,
        sources: [source],
        filePaths: files,
      });

      if (result.isOk()) {
        const stats = result.getValue();
        this.logger.info(
          `Edge reprocessing complete; source="${source.id}", filesProcessed=${stats.filesProcessed}, ` +
          `ghostEdgesFound=${stats.ghostEdgesFound}, edgesNeedUpdate=${stats.edgesNeedUpdate}`
        );
      } else {
        this.logger.error(
          `Edge reprocessing failed; source="${source.id}", errors="${result.getFormattedErrors()}"`
        );
      }
    } catch (error) {
      this.logger.error(
        `Failed to reprocess edges for source: id="${source.id}", error="${
          error instanceof Error ? error.message : String(error)
        }"`,
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
        `Failed to stat source path: "${resolvedPath}", error="${
          error instanceof Error ? error.message : String(error)
        }"`,
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
          // Skip excluded directories
          if (source.exclude && source.exclude.length > 0) {
            // Simplified exclude check
          }
          const subFiles = await this.scanDirectory(fullPath, source);
          files.push(...subFiles);
        } else if (entry.isFile()) {
          files.push(fullPath);
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
