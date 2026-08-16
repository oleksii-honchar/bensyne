import { ContentChunk } from '../../domain/content-chunk.entity';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { Result } from '../../utils/result';

/**
 * Strategy interface for chunking files.
 * Allows per-source selection of chunking behavior.
 */
export interface BaseChunkingStrategy {
  chunkFile(
    content: string,
    filePath: string,
    sourceId: string,
    sourceConfig: WatchSourceConfig,
  ): Promise<Result<ContentChunk[]>>;
}
