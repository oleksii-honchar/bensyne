import * as fs from 'fs/promises';
import * as path from 'path';
import { ContentChunk, FILE_ROLES } from '../../domain/content-chunk.entity';
import { SessionMetadata } from '../../domain/session-metadata.type';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { SessionMetadataService } from '../../infrastructure/services/session-metadata.service';
import { generateId } from '../../utils/big-endian-id';
import { Result } from '../../utils/result';
import { splitFrontmatter } from '../../utils/strategy-utils';
import { BaseChunkingStrategy } from './base-chunking-strategy';
import { MastraChunkingService } from './mastra-chunking.service';

/**
 * Walks up the directory tree from the given file path to find session.md.
 * Returns the directory containing session.md, or the parent directory of the file as fallback.
 */
async function locateSessionRoot(filePath: string): Promise<string> {
  let currentDir = path.dirname(filePath);

  while (currentDir) {
    const sessionMdPath = path.join(currentDir, 'session.md');
    try {
      await fs.stat(sessionMdPath);
      return currentDir;
    } catch {
      // session.md not found at this level, go up
      const parent = path.dirname(currentDir);
      if (parent === currentDir) {
        // Reached root, stop
        break;
      }
      currentDir = parent;
    }
  }

  // Fallback: parent directory of the given file path
  return path.dirname(filePath);
}

/**
 * Maps SessionMetadata fields to dot-notation keys for chunk metadata.
 * Chunk metadata uses a flat key-value structure, so session fields are
 * prefixed with "session." to namespace them alongside other metadata (filePath, sourceId, etc.).
 */
function formatSessionMetadata(metadata: SessionMetadata): Record<string, string> {
  return {
    'session.id': metadata.sessionId,
    'session.createdAt': metadata.createdAt,
    'session.status': metadata.status,
    'session.phase': metadata.phase,
    'session.nextAgent': metadata.nextAgent,
  };
}

/**
 * Session-aware chunking strategy that:
 * 1. Locates parent session.md by walking up from the file path
 * 2. Extracts session metadata via SessionMetadataService
 * 3. Splits frontmatter from body
 * 4. Creates frontmatter chunk with high importance (0.9)
 * 5. Chunks body via MastraChunkingService
 * 6. Enriches all chunks with session metadata
 */
export class AgentSessionChunkingStrategy implements BaseChunkingStrategy {
  constructor(
    private readonly sessionMetadataService: SessionMetadataService,
    private readonly mastraChunkingService: MastraChunkingService,
    private readonly logger: BasePinoLogger,
  ) {}

  async chunkFile(
    content: string,
    filePath: string,
    sourceId: string,
    _sourceConfig: WatchSourceConfig,
  ): Promise<Result<ContentChunk[]>> {
    // 1. Locate parent session.md
    const sessionPath = await locateSessionRoot(filePath);

    // 2. Extract session metadata
    const sessionMetadataResult = await this.sessionMetadataService.extract(sessionPath);
    const sessionMetadata = sessionMetadataResult.isOk()
      ? sessionMetadataResult.getValue()
      : { sessionId: '', createdAt: '', status: '', phase: '', nextAgent: '' };

    // 3. Split frontmatter from body
    const { frontmatter, body } = splitFrontmatter(content);

    // 4. Create frontmatter chunk if present
    const chunks: ContentChunk[] = [];
    if (frontmatter) {
      chunks.push(this.createFrontmatterChunk(frontmatter, filePath, sourceId, sessionMetadata));
    }

    // 5. Chunk body with Mastra
    const bodyChunksResult = await this.mastraChunkingService.chunkFile(body, filePath, sourceId);
    const bodyChunks = bodyChunksResult.isOk() ? bodyChunksResult.getValue() : [];

    // 6. Enrich all chunks with session metadata
    const allChunks = [...chunks, ...bodyChunks];
    const enriched = allChunks.map(chunk => this.enrichWithSessionMetadata(chunk, sessionMetadata));

    return Result.ok(enriched);
  }

  private createFrontmatterChunk(
    frontmatter: string,
    filePath: string,
    sourceId: string,
    sessionMetadata: SessionMetadata,
  ): ContentChunk {
    return ContentChunk.of({
      id: generateId(),
      text: `---\n${frontmatter}\n---`,
      chunkIndex: 0,
      totalChunks: 1,
      sectionHeader: 'Frontmatter',
      breadcrumb: filePath,
      fileRole: FILE_ROLES.DOCS,
      oversized: false,
      metadata: {
        filePath,
        sourceId,
        ...formatSessionMetadata(sessionMetadata),
      },
      importance: 0.9,
      tags: ['frontmatter', 'metadata'],
      memoryBank: 'default',
    }).getValue();
  }

  private enrichWithSessionMetadata(chunk: ContentChunk, sessionMetadata: SessionMetadata): ContentChunk {
    const existingMeta = chunk.metadata ?? {};
    const enrichedMeta = {
      ...existingMeta,
      ...formatSessionMetadata(sessionMetadata),
    };

    return ContentChunk.of({
      ...chunk.toJson(),
      metadata: enrichedMeta,
    }).getValue();
  }
}
