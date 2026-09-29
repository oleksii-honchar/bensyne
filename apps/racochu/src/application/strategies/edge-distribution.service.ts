import { Injectable } from '@nestjs/common';
import { ContentChunk, FILE_ROLES, FileEdge } from '../../domain/content-chunk.entity';
import { RememberRequestSerializer } from '../../infrastructure/mnemosyne/remember-request.serializer';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';

/**
 * Distributes cross-reference edges across chunks to prevent any single chunk
 * from exceeding the byte-safety limit (8000 bytes).
 *
 * Strategy:
 * 1. Distribute edges proportionally across chunks based on text weight
 * 2. Validate each chunk's serialized size
 * 3. If a chunk is oversized, move excess edges to the next chunk (cascading)
 */
@Injectable()
export class EdgeDistributionService {
  private static readonly MAX_REQUEST_BYTES = 8000;
  private static readonly MAX_REDIST_PASSES = 5;

  private readonly serializer = new RememberRequestSerializer();

  constructor(private readonly logger: BasePinoLogger) {
    this.logger = this.logger.child({ component: 'EdgeDistributionService' });
  }

  /**
   * Distribute cross-reference edges across body chunks proportionally by text weight.
   * Skips frontmatter chunks (index 0 if it's a frontmatter chunk).
   */
  distributeEdges(edges: FileEdge[], chunks: ContentChunk[]): ContentChunk[] {
    if (edges.length === 0 || chunks.length === 0) {
      return chunks;
    }

    // Identify body chunks (skip frontmatter chunk at index 0 if present)
    let bodyStartIndex = 0;
    if (chunks.length > 1 && chunks[0].sectionHeader === 'Frontmatter') {
      bodyStartIndex = 1;
    }

    const bodyChunks = chunks.slice(bodyStartIndex);
    if (bodyChunks.length === 0) {
      return chunks;
    }

    // Distribute edges evenly across body chunks
    const edgesPerChunk = Math.floor(edges.length / bodyChunks.length);
    const remainder = edges.length % bodyChunks.length;

    let edgeIndex = 0;
    for (let i = 0; i < bodyChunks.length; i++) {
      // First 'remainder' chunks get one extra edge
      const count = edgesPerChunk + (i < remainder ? 1 : 0);
      const chunkEdges = edges.slice(edgeIndex, edgeIndex + count);

      if (chunkEdges.length > 0) {
        const chunkProps = chunks[bodyStartIndex + i].toJson();
        chunkProps.edges = chunkEdges;
        chunks[bodyStartIndex + i] = ContentChunk.of(chunkProps).getValue();
      }

      edgeIndex += chunkEdges.length;
    }

    return chunks;
  }

  /**
   * Distribute remaining edges evenly across chunks, weighting by chunk text size.
   */
  private distributeRemainingEdges(edges: FileEdge[], chunks: ContentChunk[]): void {
    const totalTextLength = chunks.reduce((sum, c) => sum + c.text.length, 0);

    // Calculate how many edges each chunk should get
    const edgesPerChunk = chunks.map(chunk => {
      const proportion = chunk.text.length / totalTextLength;
      return Math.floor(edges.length * proportion);
    });

    // Distribute edges
    let edgeIndex = 0;
    for (let i = 0; i < chunks.length && edgeIndex < edges.length; i++) {
      const count = edgesPerChunk[i];
      const chunkEdges = edges.slice(edgeIndex, edgeIndex + count);

      if (chunkEdges.length > 0) {
        const chunkProps = chunks[i].toJson();
        chunkProps.edges = [...(chunkProps.edges ?? []), ...chunkEdges];
        chunks[i] = ContentChunk.of(chunkProps).getValue();
      }

      edgeIndex += chunkEdges.length;
    }

    // Any remaining edges go to the last chunk
    if (edgeIndex < edges.length) {
      const remaining = edges.slice(edgeIndex);
      const lastChunk = chunks[chunks.length - 1];
      const chunkProps = lastChunk.toJson();
      chunkProps.edges = [...(chunkProps.edges ?? []), ...remaining];
      chunks[chunks.length - 1] = ContentChunk.of(chunkProps).getValue();
    }
  }

  /**
   * Validate each chunk's serialized size and redistribute excess edges.
   * Returns the validated chunks.
   */
  validateAndRedistribute(chunks: ContentChunk[]): ContentChunk[] {
    if (chunks.length === 0) {
      return chunks;
    }

    for (let pass = 0; pass < EdgeDistributionService.MAX_REDIST_PASSES; pass++) {
      let redistributed = false;

      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        const serialized = this.serializer.buildAndSerialize(chunk);
        const size = Buffer.byteLength(serialized, 'utf8');

        if (size > EdgeDistributionService.MAX_REQUEST_BYTES && chunk.edges !== undefined && chunk.edges.length > 0) {
          // Try to move edges to next chunk
          if (i + 1 < chunks.length) {
            const moved = this.moveEdgesToNextChunk(chunks, i, i + 1);
            if (moved > 0) {
              redistributed = true;
              this.logger.info(
                `Redistributed ${moved} edges from chunk ${i} to chunk ${i + 1}`,
              );
            }
          } else {
            // Last chunk — move edges to previous chunk
            const moved = this.moveEdgesToPrevChunk(chunks, i, i - 1);
            if (moved > 0) {
              redistributed = true;
            }
          }
        }
      }

      if (!redistributed) {
        break;
      }
    }

    return chunks;
  }

  /**
   * Move edges from source chunk to target chunk until source fits under limit.
   * Returns the number of edges moved.
   */
  private moveEdgesToNextChunk(
    chunks: ContentChunk[],
    sourceIndex: number,
    targetIndex: number,
  ): number {
    let source = chunks[sourceIndex];
    if (source.edges === undefined || source.edges.length === 0) {
      return 0;
    }

    let target = chunks[targetIndex];
    let moved = 0;

    while (source.edges !== undefined && source.edges.length > 0) {
      const sourceSerialized = this.serializer.buildAndSerialize(source);
      const sourceSize = Buffer.byteLength(sourceSerialized, 'utf8');

      if (sourceSize <= EdgeDistributionService.MAX_REQUEST_BYTES) {
        break; // source now fits
      }

      // Move one edge to target
      const edgeToMove = source.edges.pop()!;
      const targetEdges = target.edges ?? [];
      targetEdges.push(edgeToMove);

      const sourceProps = source.toJson();
      sourceProps.edges = source.edges;
      source = ContentChunk.of(sourceProps).getValue();

      const targetProps = target.toJson();
      targetProps.edges = targetEdges;
      target = ContentChunk.of(targetProps).getValue();

      moved++;
    }

    chunks[sourceIndex] = source;
    chunks[targetIndex] = target;
    return moved;
  }

  /**
   * Move edges from source chunk to previous chunk (for last-chunk overflow).
   * Returns the number of edges moved.
   */
  private moveEdgesToPrevChunk(
    chunks: ContentChunk[],
    sourceIndex: number,
    targetIndex: number,
  ): number {
    let source = chunks[sourceIndex];
    if (source.edges === undefined || source.edges.length === 0) {
      return 0;
    }

    let target = chunks[targetIndex];
    let moved = 0;

    while (source.edges !== undefined && source.edges.length > 0) {
      const sourceSerialized = this.serializer.buildAndSerialize(source);
      const sourceSize = Buffer.byteLength(sourceSerialized, 'utf8');

      if (sourceSize <= EdgeDistributionService.MAX_REQUEST_BYTES) {
        break;
      }

      const edgeToMove = source.edges.pop()!;
      const targetEdges = target.edges ?? [];
      targetEdges.push(edgeToMove);

      const sourceProps = source.toJson();
      sourceProps.edges = source.edges;
      source = ContentChunk.of(sourceProps).getValue();

      const targetProps = target.toJson();
      targetProps.edges = targetEdges;
      target = ContentChunk.of(targetProps).getValue();

      moved++;
    }

    chunks[sourceIndex] = source;
    chunks[targetIndex] = target;
    return moved;
  }
}