import { Injectable } from '@nestjs/common';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { WatchSourceConfig } from '../infrastructure/config/config-schemas';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { BaseUseCase } from '../utils/base-use-case';
import { Result } from '../utils/result';
import { ErrorWithDetails } from '../utils/error-with-details';
import { z } from 'zod';

const reprocessEdgesParamsSchema = z.object({
  sourceId: z.string().min(1),
  sources: z.array(z.any()).min(1),
  filePaths: z.array(z.string()).min(1),
});

export type ReprocessEdgesParams = z.infer<typeof reprocessEdgesParamsSchema>;

export interface ReprocessEdgesResult {
  filesProcessed: number;
  ghostEdgesFound: number;
  edgesNeedUpdate: number;
  edgesPruned: number;
}

/**
 * Two-Pass Reprocessing for Ghost-Edge Cleanup (Option B).
 *
 * Pass 1: Build a map of file path -> file ID for all files in the source.
 * Pass 2: For each file, expand its outgoing edges and verify each target exists.
 *         Log ghost edges (targets that don't exist) and edges needing updates.
 *
 * This runs after all files in a source have been reprocessed.
 */
@Injectable()
export class ReprocessEdgesUseCase extends BaseUseCase<ReprocessEdgesParams, ReprocessEdgesResult> {
  constructor(
    private readonly bensyneClient: BensyneClient,
    baseLogger: BasePinoLogger,
  ) {
    super(baseLogger);
    this.logger = this.logger.child({ component: 'ReprocessEdgesUseCase' });
  }

  protected validateParams(params: ReprocessEdgesParams): Result<ReprocessEdgesParams> {
    const parsed = reprocessEdgesParamsSchema.safeParse(params);
    if (!parsed.success) {
      return Result.ko([
        new ErrorWithDetails(
          'Invalid reprocess-edges params: ' + parsed.error.message,
          'InvalidReprocessEdgesParams',
        ),
      ]);
    }
    return Result.ok(parsed.data);
  }

  protected async executeInternal(params: ReprocessEdgesParams): Promise<Result<ReprocessEdgesResult>> {
    const { sourceId, sources, filePaths } = params;
    this.logger.info(`Starting edge reprocessing; sourceId="${sourceId}", files=${filePaths.length}`);

    const source = sources.find((s) => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      return Result.ok({ filesProcessed: 0, ghostEdgesFound: 0, edgesNeedUpdate: 0, edgesPruned: 0 });
    }

    const memoryBank = source.memoryBank;

    // Pass 1: Build file ID map for all files in the source
    this.logger.info(`Pass 1: Building file ID map for source; id="${sourceId}", files=${filePaths.length}`);
    const filePathToId = await this.buildFileIdMap(filePaths, memoryBank);
    this.logger.info(`Pass 1 complete: ${filePathToId.size} files mapped`);

    // Pass 2: Check edges for each file
    this.logger.info(`Pass 2: Checking edges for each file`);
    const stats = { filesProcessed: 0, ghostEdgesFound: 0, edgesNeedUpdate: 0, edgesPruned: 0 };

    for (const filePath of filePaths) {
      stats.filesProcessed++;
      const fileId = filePathToId.get(filePath);
      if (!fileId) {
        this.logger.debug(`File not in ID map, skipping edge check; path="${filePath}"`);
        continue;
      }

      try {
        await this.checkFileEdges(filePath, fileId, memoryBank, filePathToId, stats);
      } catch (error) {
        this.logger.error(
          `Error checking edges for file; path="${filePath}", error="${
            error instanceof Error ? error.message : String(error)
          }"`
        );
      }
    }

    this.logger.info(
      `Edge reprocessing complete; sourceId="${sourceId}", filesProcessed=${stats.filesProcessed}, ` +
      `ghostEdgesFound=${stats.ghostEdgesFound}, edgesNeedUpdate=${stats.edgesNeedUpdate}`
    );

    return Result.ok(stats);
  }

  /**
   * Pass 1: Build a map from file path to file ID by calling getFileChunks for each file.
   */
  private async buildFileIdMap(
    filePaths: string[],
    memoryBank: string,
  ): Promise<Map<string, string>> {
    const filePathToId = new Map<string, string>();

    for (const filePath of filePaths) {
      try {
        const chunksResult = await this.bensyneClient.getFileChunks(filePath, memoryBank);
        if (chunksResult.isKo()) {
          this.logger.debug(`getFileChunks failed for file; path="${filePath}"`);
          continue;
        }

        const chunksInfo = chunksResult.getValue();
        if (chunksInfo.status === 'present' && chunksInfo.fileId) {
          filePathToId.set(filePath, chunksInfo.fileId);
        } else {
          this.logger.debug(`File not present in bank; path="${filePath}"`);
        }
      } catch (error) {
        this.logger.debug(`Error getting file chunks; path="${filePath}", error="${
          error instanceof Error ? error.message : String(error)
        }"`);
      }
    }

    return filePathToId;
  }

  /**
   * Pass 2: Check all outgoing edges for a file and verify target existence.
   */
  private async checkFileEdges(
    filePath: string,
    fileId: string,
    memoryBank: string,
    filePathToId: Map<string, string>,
    stats: ReprocessEdgesResult,
  ): Promise<void> {
    this.logger.debug(`Checking edges for file; path="${filePath}", fileId="${fileId}"`);

    const edgesResult = await this.bensyneClient.expandFileRelations(
      fileId,
      memoryBank,
      ['file_ref']
    );

    if (edgesResult.isKo()) {
      this.logger.debug(`expandFileRelations failed; fileId="${fileId}"`);
      return;
    }

    const edges = edgesResult.getValue();
    if (edges.length === 0) {
      this.logger.debug(`No outgoing edges for file; path="${filePath}"`);
      return;
    }

    this.logger.debug(`File has ${edges.length} outgoing edges; path="${filePath}"`);

    for (const edge of edges) {
      await this.checkEdge(edge, memoryBank, filePathToId, stats);
    }
  }

  /**
   * Check a single edge: verify target exists, log ghost edges, suggest updates.
   */
  private async checkEdge(
    edge: { source_file_id: string; target_file_id: string; relation_type: string },
    memoryBank: string,
    filePathToId: Map<string, string>,
    stats: ReprocessEdgesResult,
  ): Promise<void> {
    this.logger.debug(
      `Checking edge; source="${edge.source_file_id}", target="${edge.target_file_id}", type="${edge.relation_type}"`
    );

    // Check if the target file ID exists by trying to get its file chunks
    // We don't have the target's file path directly, so we check if any file maps to it
    const targetFileExists = this.targetFileIdExists(edge.target_file_id, filePathToId);

    if (targetFileExists) {
      return; // Edge is valid
    }

    // Target doesn't exist — this is a ghost edge
    stats.ghostEdgesFound++;
    this.logger.warn(
      `Ghost edge found; source="${edge.source_file_id}", target="${edge.target_file_id}", type="${edge.relation_type}"`
    );

    // Attempt to resolve the real target by checking if a file with a similar path exists
    // For now, we just log that an update would be needed
    stats.edgesNeedUpdate++;
    this.logger.warn(
      `Edge needs update; source="${edge.source_file_id}", target="${edge.target_file_id}" — real target not found, update would require bensyne-mcp endpoint`
    );

    // Prune the phantom edge stub
    this.logger.debug(
      `Pruning phantom edge stub; source="${edge.source_file_id}", target="${edge.target_file_id}", type="${edge.relation_type}"`
    );
    const pruneResult = await this.bensyneClient.prunePhantomEdgeStub(
      edge.source_file_id,
      edge.target_file_id,
      memoryBank,
      edge.relation_type
    );

    if (pruneResult.isOk()) {
      stats.edgesPruned++;
      this.logger.info(
        `Phantom edge stub pruned; source="${edge.source_file_id}", target="${edge.target_file_id}"`
      );
    } else {
      const errors = pruneResult.getErrors();
      this.logger.error(
        `Failed to prune phantom edge stub; source="${edge.source_file_id}", target="${edge.target_file_id}", errors=${errors.map(e => e.message).join(', ')}`
      );
    }
  }

  /**
   * Check if a target file ID exists in our file ID map.
   */
  private targetFileIdExists(fileId: string, filePathToId: Map<string, string>): boolean {
    for (const mappedId of filePathToId.values()) {
      if (mappedId === fileId) {
        return true;
      }
    }
    return false;
  }
}
