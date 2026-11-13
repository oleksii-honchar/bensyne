import { Injectable } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { ReprocessEdgesUseCase } from '../../use-cases/reprocess-edges.use-case';
import { isPathExcluded, isPathInScope } from '../glob-matcher';

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

    const source = sources.find(s => s.id === sourceId);
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
            `ghostEdgesFound=${stats.ghostEdgesFound}, edgesNeedUpdate=${stats.edgesNeedUpdate}`,
        );
      } else {
        this.logger.error(
          `Edge reprocessing failed; source="${source.id}", errors="${result.getFormattedErrors()}"`,
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

  /**
   * R1: enumerate ALL declared roots of the source (`resolvedPaths`; a
   * single-`path` source carries the normalized `[path]` shape and stays
   * byte-identical). Union in declared-root order, de-duplicated by resolved
   * absolute path.
   */
  private async getFiles(source: WatchSourceConfig): Promise<string[]> {
    const merged: string[] = [];
    const seen = new Set<string>();

    for (const rootPath of this.declaredRoots(source)) {
      const rootFiles = await this.scanRoot(rootPath, source);
      for (const file of rootFiles) {
        const key = path.resolve(file);
        if (!seen.has(key)) {
          seen.add(key);
          merged.push(file);
        }
      }
    }

    return merged;
  }

  /** Resolved, de-duplicated root paths in declared order. */
  private declaredRoots(source: WatchSourceConfig): string[] {
    const declared = source.resolvedPaths ?? [source.path];
    const roots: string[] = [];
    for (const rootPath of declared) {
      const resolved = this.resolvePath(rootPath);
      if (!roots.includes(resolved)) {
        roots.push(resolved);
      }
    }
    return roots;
  }

  private async scanRoot(resolvedRoot: string, source: WatchSourceConfig): Promise<string[]> {
    try {
      const stats = await fs.stat(resolvedRoot);
      if (!stats.isDirectory()) {
        this.logger.warn(`Source path is not a directory; "${resolvedRoot}"`);
        return [];
      }

      return this.scanDirectory(resolvedRoot, source, resolvedRoot);
    } catch (error) {
      this.logger.error(
        `Failed to stat source path: "${resolvedRoot}", error="${
          error instanceof Error ? error.message : String(error)
        }"`,
      );
      return [];
    }
  }

  private async scanDirectory(
    dirPath: string,
    source: WatchSourceConfig,
    sourceRoot: string,
  ): Promise<string[]> {
    const files: string[] = [];

    try {
      const entries = await fs.readdir(dirPath, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(dirPath, entry.name);
        const relPath = path.relative(sourceRoot, fullPath);

        if (entry.isDirectory()) {
          // Skip excluded directories using the shared glob matcher — the
          // behavior the empty stub in be40a0f documented but never had
          // (ADR-3 alignment). Descent stays EXCLUDE-ONLY: include patterns
          // match files, never directory paths (invariant I2).
          if (isPathExcluded(relPath, source.exclude)) {
            continue;
          }
          const subFiles = await this.scanDirectory(fullPath, source, sourceRoot);
          files.push(...subFiles);
        } else if (entry.isFile()) {
          // File emission uses the shared scope check: include allow-list
          // (when present) ∧ ¬excluded — one composition, same semantics as
          // every other enforcement point (spec §5 EP3).
          if (isPathInScope(relPath, source.include, source.exclude)) {
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
