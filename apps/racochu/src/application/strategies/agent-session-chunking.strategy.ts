import { Injectable } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as os from 'os';
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
 * absolute paths. Performs exactly ONE readdir of R (plus cheap, targeted
 * `stat` checks for each companion dir's canonical file). A companion dir
 * contributes its canonical file ONLY if that file actually exists on disk.
 * On any fs error, returns an empty/partial array (never throws).
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

  // Companion directories — resolve to their canonical file, but ONLY if that
  // specific file actually exists on disk (a present dir alone is not enough).
  for (const dir of COMPANION_DIRS) {
    if (entryNames.has(dir)) {
      const fileName = COMPANION_DIR_FILES[dir];
      if (fileName) {
        const candidate = path.join(sessionRoot, dir, fileName);
        try {
          const stats = await fs.stat(candidate);
          if (stats.isFile()) {
            paths.push(candidate);
          }
        } catch {
          // canonical file absent or unreadable → treat as absent, skip
        }
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

// ---------------------------------------------------------------------------
// Producer-side content cross-reference edges (D42 §2.2)
//
// Turns in-content references to other session files into typed
// `cross_reference` file edges. Cross-session refs are ALLOWED (user ruling
// 2026-08-19): there is NO session-containment guard — the existence gate is
// the only filter.
// ---------------------------------------------------------------------------

const XREF_MAX_DEPTH = 4;
const XREF_MAX_FILES = 200;
const XREF_MAX_TOKENS = 200;
const XREF_PATH_TOKEN_RE = /[\w./~-]+\.md\b/g;

/** Expands a leading `~` / `~/` to the OS home directory. */
export function expandTilde(token: string): string {
  if (token === '~') {
    return os.homedir();
  }
  if (token.startsWith('~/')) {
    return path.join(os.homedir(), token.slice(2));
  }
  return token;
}

/** Recursively collects *.md absolute paths under dir, bounded by maxDepth/maxFiles. */
async function walkMdFiles(dir: string, depth: number, files: string[]): Promise<void> {
  if (depth > XREF_MAX_DEPTH || files.length >= XREF_MAX_FILES) {
    return;
  }
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (files.length >= XREF_MAX_FILES) {
      return;
    }
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await walkMdFiles(fullPath, depth + 1, files);
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      files.push(fullPath);
    }
  }
}

/**
 * Lists all *.md absolute paths under sessionRoot (recursive, bounded:
 * maxDepth 4, maxFiles 200). On any fs error returns [] (never throws).
 */
export async function listSessionMdFiles(sessionRoot: string): Promise<string[]> {
  try {
    const files: string[] = [];
    await walkMdFiles(sessionRoot, 1, files);
    return files;
  } catch {
    return [];
  }
}

function escapeRegexChars(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Builds `cross_reference` edges from in-content file references (D42 §2.2).
 *
 * Pass 1 (path-pattern, primary): regex token extraction, tilde expansion,
 * resolution (absolute as-is, relative vs session root), self-skip, NO
 * containment guard, existence gate (sessionFiles membership or fs.stat).
 *
 * Pass 2 (basename, conservative): distinctive basenames (under archive/, or
 * session.md, or unique in the tree), standalone-token match, collision-skip.
 *
 * Emits one edge per unique target (strength 0.7, absolute target_path).
 */
export async function buildCrossReferenceEdges(
  content: string,
  filePath: string,
  sessionRoot: string,
  sessionFiles: string[],
): Promise<FileEdge[]> {
  const normalizedSelf = path.resolve(filePath);
  const sessionFileSet = new Set(sessionFiles.map(f => path.resolve(f)));
  const targets = new Set<string>();

  // --- Pass 1: path-pattern refs ---
  const uniqueTokens = [...new Set(content.match(XREF_PATH_TOKEN_RE) ?? [])].slice(0, XREF_MAX_TOKENS);
  for (const token of uniqueTokens) {
    const expanded = expandTilde(token);
    const resolved = path.isAbsolute(expanded) ? path.resolve(expanded) : path.resolve(sessionRoot, expanded);

    if (resolved === normalizedSelf) {
      continue; // self-skip
    }
    if (sessionFileSet.has(resolved)) {
      targets.add(resolved);
      continue;
    }
    // Existence gate — the ONLY filter (cross-session refs allowed, no containment guard)
    try {
      const stats = await fs.stat(resolved);
      if (stats.isFile()) {
        targets.add(resolved);
      }
    } catch {
      // missing target → no edge
    }
  }

  // --- Pass 2: conservative basename refs ---
  const byBasename = new Map<string, string[]>();
  for (const f of sessionFiles) {
    const resolved = path.resolve(f);
    const base = path.basename(resolved);
    const existing = byBasename.get(base) ?? [];
    existing.push(resolved);
    byBasename.set(base, existing);
  }

  for (const [base, filesForBase] of byBasename) {
    // collision-skip: basename maps to >1 file in the tree
    if (filesForBase.length > 1) {
      continue;
    }
    const candidate = filesForBase[0];
    if (targets.has(candidate)) {
      continue; // already targeted by Pass 1
    }
    const rel = path.relative(sessionRoot, candidate);
    const underArchive = rel.includes(`${path.sep}archive${path.sep}`);
    const isSessionMd = base === 'session.md';
    const uniqueInTree = filesForBase.length === 1;
    if (!underArchive && !isSessionMd && !uniqueInTree) {
      continue;
    }
    // Standalone token match: basename not preceded by a path char and not
    // followed by a word char (avoids double-counting Pass-1 path refs).
    const standaloneRe = new RegExp(`(?<![\\w./-])${escapeRegexChars(base)}(?!\\w)`, 'g');
    if (standaloneRe.test(content)) {
      if (candidate !== normalizedSelf) {
        targets.add(candidate);
      }
    }
  }

  // --- Emit: one edge per unique target ---
  const edges: FileEdge[] = [];
  for (const target of targets) {
    edges.push({
      target_path: target,
      relation_type: 'cross_reference',
      strength: 0.7,
      description: `content reference to ${path.relative(sessionRoot, target)}`,
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

    // 3. List companion artifacts (fs error ⇒ empty list, chunking still succeeds)
    const companions = await this.listCompanionsSafe(sessionPath);
    const edges = buildCompanionEdges(filePath, sessionPath, companions);

    // 3b. Build cross-reference edges from in-content refs to archived material (D42 §2.3).
    //     Walks the session tree for *.md files; on fs error degrades to no cross-ref edges.
    const sessionFiles = await this.listSessionFilesSafe(sessionPath);
    const xrefEdges = await this.buildCrossReferenceEdgesSafe(content, filePath, sessionPath, sessionFiles);
    const allEdges = [...edges, ...xrefEdges];

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
      this.enrichWithSessionMetadataAndEdges(chunk, sessionMetadata, allEdges),
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

  private async listSessionFilesSafe(sessionRoot: string): Promise<string[]> {
    try {
      return await listSessionMdFiles(sessionRoot);
    } catch (error) {
      this.logger.debug('Failed to list session files for cross-reference walk', {
        sessionRoot,
        error: String(error),
      });
      return [];
    }
  }

  private async buildCrossReferenceEdgesSafe(
    content: string,
    filePath: string,
    sessionRoot: string,
    sessionFiles: string[],
  ): Promise<FileEdge[]> {
    try {
      return await buildCrossReferenceEdges(content, filePath, sessionRoot, sessionFiles);
    } catch (error) {
      this.logger.debug('Failed to build cross-reference edges', {
        filePath,
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
