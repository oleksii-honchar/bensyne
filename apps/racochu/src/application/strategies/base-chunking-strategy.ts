import { ContentChunk } from '../../domain/content-chunk.entity';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { Result } from '../../utils/result';

/**
 * Per-chunking-run options. `skipEnrichment` forces the enrichment-free path
 * (no enhancement pipeline, no Mastra extractMetadata LLM block) regardless of
 * runtime config — used by recover's cheap chunk enumeration (spec §4.3, ADR-2).
 */
export interface ChunkFileOptions {
  skipEnrichment?: boolean;
}

/**
 * Strategy interface for chunking files.
 * Allows per-source selection of chunking behavior.
 *
 * NOTE (spec §4.3 / ADR-2 signature-collision warning): the `options` override
 * is the optional 5th parameter. The 4th slot is `sourceConfig` at every call
 * site — a skip flag in the 4th position would silently receive the config
 * object. Implementations with fewer params remain compatible (JS drops extras).
 */
export interface BaseChunkingStrategy {
  chunkFile(
    content: string,
    filePath: string,
    sourceId: string,
    sourceConfig: WatchSourceConfig,
    options?: ChunkFileOptions,
  ): Promise<Result<ContentChunk[]>>;
}
