import { ContentChunk, FileEdge } from '../../domain/content-chunk.entity';
import { sourceTypeSchema } from '../config/source-types';

/**
 * Unified chunk contract v1 — `metadata` payload of the rememberMemory call.
 * Source of truth: materials/unified-chunk-contract.md (session 260811-0000-bensyne-file-metadata).
 *
 * Rules applied here:
 * - snake_case keys only; `contract_version: 1` always present.
 * - `file_path` triggers materialization in bensyne; absent ⇒ plain memory.
 * - `extra` is the ONLY extension point: source-specific legacy metadata keys
 *   (dotted keys like `session.*` / `note.*`, and any other string-valued key
 *   not consumed by a v1 field) land here verbatim — never new top-level dialects.
 * - Hash discipline (contract rule 4b): the two hashes live ONLY in `metadata`,
 *   never at the remember top level (the rememberMemory tool schema has no `hash`
 *   argument — FastMCP's strict schema rejects one). `metadata.chunk_hash` is the
 *   sha256 of this chunk's exact text (computed per chunk by ChunkContentUseCase);
 *   `metadata.file_hash` is the sha256 of the whole source file (computed once at
 *   process-file time by FileHasherService in ProcessFileUseCase). Both reach this
 *   DTO pre-wire as camelCase keys (`chunkHash` / `fileHash`) in the chunk's
 *   internal metadata; this DTO is the camelCase→snake_case translation boundary
 *   (D12). This DTO REUSES those values — it never computes a hash. When a producer
 *   could not compute a hash (non-fatal omission, e.g. content-aware plain-memory
 *   path) the corresponding `metadata.*` key is ABSENT (not null, not empty) and
 *   bensyne degrades gracefully (upsert-only, no rebuild).
 */
export interface UnifiedChunkContractV1Metadata {
  contract_version: 1;
  file_path?: string;
  chunk_index: number;
  total_chunks: number;
  section_header: string;
  start_line?: number;
  end_line?: number;
  source_type?: string;
  file_role: string;
  language?: string;
  file_hash?: string;
  chunk_hash?: string;
  summary?: string | null;
  parent_unit?: { ref: string; summary?: string | null };
  edges?: FileEdge[];
  tags: string[];
  extra?: Record<string, string>;
}

/**
 * Payload shape for the rememberMemory MCP tool call arguments.
 * Maps domain Chunk entity properties to the unified chunk contract v1.
 */
export interface MnemosyneRememberPayload {
  content: string;
  memory_bank: string;
  importance: number;
  source: string;
  metadata: UnifiedChunkContractV1Metadata;
}

/**
 * DTO for transforming a Chunk domain entity into the Mnemosyne remember payload.
 * Encapsulates the mapping logic so BensyneClient stays focused on transport.
 */
export class BensyneRememberDto {
  static fromChunk(chunk: ContentChunk): MnemosyneRememberPayload {
    const metadata = chunk.metadata ?? {};

    // Keys consumed by explicit v1 fields — everything else goes to `extra`.
    const fileHash = metadata.fileHash;
    const chunkHash = metadata.chunkHash;
    const filePath = metadata.filePath ?? (chunk.breadcrumb || undefined);
    // D29: the chunk's stamped sourceType (from the originating watch source) passes
    // through zod-validated — the 4-value axis is exactly what bensyne SourceType
    // accepts. Missing/off-axis ⇒ key omitted (bensyne degrades to `unknown`).
    // `sourceId` (the watch-source id) is a consumed internal key, never a type source.
    const sourceType = metadata.sourceType ? sourceTypeSchema.safeParse(metadata.sourceType).data : undefined;

    const extra: Record<string, string> = {};
    for (const [key, value] of Object.entries(metadata)) {
      if (
        key === 'fileHash' ||
        key === 'chunkHash' ||
        key === 'filePath' ||
        key === 'sourceId' ||
        key === 'sourceType' ||
        key === 'mastraDocSummary'
      )
        continue;
      extra[key] = value;
    }

    return {
      content: chunk.text,
      memory_bank: chunk.memoryBank,
      importance: chunk.importance,
      source: chunk.memoryBank,
      metadata: {
        contract_version: 1,
        ...(filePath !== undefined && filePath !== '' && { file_path: filePath }),
        chunk_index: chunk.chunkIndex,
        total_chunks: chunk.totalChunks,
        section_header: chunk.sectionHeader,
        ...(chunk.startLine !== undefined && { start_line: chunk.startLine }),
        ...(chunk.endLine !== undefined && { end_line: chunk.endLine }),
        ...(sourceType !== undefined && { source_type: sourceType }),
        file_role: chunk.fileRole,
        ...(chunk.language !== undefined && { language: chunk.language }),
        ...(fileHash !== undefined && { file_hash: fileHash }),
        ...(chunkHash !== undefined && { chunk_hash: chunkHash }),
        summary: metadata.mastraDocSummary ?? null,
        ...this.parentUnitField(metadata),
        ...(chunk.edges !== undefined && { edges: chunk.edges }),
        tags: chunk.tags,
        ...(Object.keys(extra).length > 0 && { extra }),
      },
    };
  }

  private static parentUnitField(
    metadata: Record<string, string>,
  ): { parent_unit: { ref: string; summary?: string } } | Record<string, never> {
    const parentUnit = this.mapParentUnit(metadata);
    return parentUnit !== undefined ? { parent_unit: parentUnit } : {};
  }

  /**
   * Derives `parent_unit` ({ref, summary}) from legacy source-specific metadata keys.
   * Agent-session chunks carry `session.id` (stable unit id ⇒ ref, prefixed per the
   * contract's example convention) and `session.status` (best available session-level
   * description ⇒ summary). Sources without a parent-unit concept (e.g. obsidian notes:
   * note ≈ file) leave it absent — degenerate case per contract rule 5 (enrichment
   * falls back to mechanical summary).
   */
  private static mapParentUnit(
    metadata: Record<string, string>,
  ): { ref: string; summary?: string } | undefined {
    const sessionId = metadata['session.id'];
    if (!sessionId) return undefined;
    const summary = metadata['session.status'] || undefined;
    return summary !== undefined ? { ref: `session-${sessionId}`, summary } : { ref: `session-${sessionId}` };
  }
}
