import { Injectable } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as path from 'path';
import { ContentChunk, FILE_ROLES, FileEdge } from '../../domain/content-chunk.entity';
import { SessionMetadata } from '../../domain/session-metadata.type';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { SessionMetadataService } from '../../infrastructure/services/session-metadata.service';
import { generateId } from '../../utils/big-endian-id';
import { Result } from '../../utils/result';
import { splitFrontmatter } from '../../utils/strategy-utils';
import { BaseChunkingStrategy } from './base-chunking-strategy';
import { MastraChunkingService } from './mastra-chunking.service';

/** Companion artifact names present in a session root (top-level entries). */
const COMPANION_FILE = 'session.md';
const COMPANION_DIRS = ['specifications', 'findings', 'decisions', 'plans', 'materials'] as const;

/** Canonical file name within each companion directory (deterministic edge target). */
const COMPANION_DIR_FILES: Record<string, string> = {
  specifications: 'spec.md',
  findings: 'findings.md',
  decisions: 'decisions.md',
  plans: 'implementation-plan.md',
  materials: 'unified-chunk-contract.md',
};

/**
 * Lists companion artifacts present in the session root R and returns their
 * absolute paths. Performs exactly ONE readdir of R. On any fs error, returns
 * an empty array (never throws).
 */
async function listCompanionArtifacts(sessionRoot: string): Promise<string[]> {
  let entries: import('fs').Dirent[];
  try {
    entries = await fs.readdir(sessionRoot, { withFileTypes: true });
  } catch {
    return [];
  }

  const paths: string[] = [];
  const entryNames = new Set(entries.map(e => e.name));

  // session.md (file)
  if (entryNames.has(COMPANION_FILE)) {
    paths.push(path.join(sessionRoot, COMPANION_FILE));
  }

  // Companion directories — resolve to their canonical file
  for (const dir of COMPANION_DIRS) {
    if (entryNames.has(dir)) {
      const fileName = COMPANION_DIR_FILES[dir];
      if (fileName) {
        paths.push(path.join(sessionRoot, dir, fileName));
      }
    }
  }

  return paths;
}

/**
 * Builds companion edges for a chunked file F in session root R.
 * - parent_child: F → R/session.md (when F is NOT session.md itself)
 * - sibling: one edge per other present companion artifact (excluding F and
 *   the session.md target already covered by parent_child)
 */
function buildCompanionEdges(filePath: string, sessionRoot: string, companions: string[]): FileEdge[] {
  if (companions.length === 0) {
    return [];
  }

  const edges: FileEdge[] = [];
  const normalizedFile = path.resolve(filePath);
  const sessionMdPath = path.join(sessionRoot, COMPANION_FILE);

  // parent_child edge when F is not session.md itself
  if (normalizedFile !== sessionMdPath && companions.includes(sessionMdPath)) {
    edges.push({
      target_path: sessionMdPath,
      relation_type: 'parent_child',
      strength: 1,
      description: 'companion artifact in session root',
    });
  }

  // sibling edges to each other present companion (excluding F and session.md)
  for (const companion of companions) {
    if (companion === normalizedFile || companion === sessionMdPath) {
      continue;
    }
    edges.push({
      target_path: companion,
      relation_type: 'sibling',
      strength: 1,
      description: 'companion artifact in session root',
    });
  }

  return edges;
}

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
@Injectable()
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

    // 3. List companion artifacts (ONE readdir; fs error ⇒ empty list, chunking still succeeds)
    const companions = await this.listCompanionsSafe(sessionPath);
    const edges = buildCompanionEdges(filePath, sessionPath, companions);

    // 4. Split frontmatter from body
    const { frontmatter, body } = splitFrontmatter(content);

    // 5. Create frontmatter chunk if present
    const chunks: ContentChunk[] = [];
    if (frontmatter) {
      chunks.push(this.createFrontmatterChunk(frontmatter, filePath, sourceId, sessionMetadata));
    }

    // 6. Chunk body with Mastra
    const bodyChunksResult = await this.mastraChunkingService.chunkFile(body, filePath, sourceId);
    const bodyChunks = bodyChunksResult.isOk() ? bodyChunksResult.getValue() : [];

    // 7. Enrich all chunks with session metadata and companion edges
    const allChunks = [...chunks, ...bodyChunks];
    const enriched = allChunks.map(chunk =>
      this.enrichWithSessionMetadataAndEdges(chunk, sessionMetadata, edges),
    );

    // 8. D41 (clarification A): the strategy composes the final chunk list, so it owns its
    //    final indices — re-index densely 0..m-1 and set totalChunks = m on every chunk.
    const finalChunks = enriched.map((chunk, idx) =>
      ContentChunk.of({
        ...chunk.toJson(),
        chunkIndex: idx,
        totalChunks: enriched.length,
      }).getValue(),
    );

    return Result.ok(finalChunks);
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

  private async listCompanionsSafe(sessionRoot: string): Promise<string[]> {
    try {
      return await listCompanionArtifacts(sessionRoot);
    } catch (error) {
      this.logger.debug('Failed to list companion artifacts in session root', {
        sessionRoot,
        error: String(error),
      });
      return [];
    }
  }

  private enrichWithSessionMetadataAndEdges(
    chunk: ContentChunk,
    sessionMetadata: SessionMetadata,
    edges: FileEdge[],
  ): ContentChunk {
    const existingMeta = chunk.metadata ?? {};
    const enrichedMeta = {
      ...existingMeta,
      ...formatSessionMetadata(sessionMetadata),
    };

    return ContentChunk.of({
      ...chunk.toJson(),
      metadata: enrichedMeta,
      ...(edges.length > 0 && { edges }),
    }).getValue();
  }
}
