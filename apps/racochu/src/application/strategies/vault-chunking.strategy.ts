import { Injectable } from '@nestjs/common';
import * as fsp from 'fs/promises';
import * as yaml from 'js-yaml';
import * as path from 'path';
import { ContentChunk, FILE_ROLES, FileEdge } from '../../domain/content-chunk.entity';
import { NoteMetadata } from '../../domain/note-metadata.type';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { generateId } from '../../utils/big-endian-id';
import { Result } from '../../utils/result';
import { extractWikilinks, splitFrontmatter } from '../../utils/strategy-utils';
import { BaseChunkingStrategy } from './base-chunking-strategy';
import { MastraChunkingService } from './mastra-chunking.service';
import { formatNoteMetadata } from './obsidian-chunking.strategy';

/** Vault index/MOC filenames (checked first — cheap, no YAML needed). */
const INDEX_FILENAMES = new Set(['_index.md', '_Vault-Home.md']);

/** Vault frontmatter keys that map to explicit NoteMetadata fields (lowercased). */
const VAULT_TYPED_KEYS = new Set(['type', 'status', 'tags', 'createdat', 'updatedat']);

/** Lazy bounded vault walk limits (spec §3.2). */
const MAX_WALK_DEPTH = 5;
const MAX_WALK_FILES = 500;

/** Chunk tag limit (contentChunkSchema tags.max(20)). */
const TAG_LIMIT = 20;

/**
 * Detects vault index/MOC files:
 * - filename is `_index.md` or `_Vault-Home.md`, OR
 * - frontmatter `type` is `index`.
 * Filename check runs first (cheap).
 */
export function isIndexFile(filePath: string, frontmatter: string | null): boolean {
  if (INDEX_FILENAMES.has(path.basename(filePath))) {
    return true;
  }
  if (frontmatter === null) {
    return false;
  }
  const record = parseFrontmatterRecord(frontmatter);
  return record !== null && record.type === 'index';
}

/**
 * Parses a YAML frontmatter string into a record.
 * Defensive: parse errors, non-objects, and scalars yield null.
 */
export function parseFrontmatterRecord(frontmatter: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = yaml.load(frontmatter);
    if (parsed === null || parsed === undefined || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null;
    }
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Extracts vault-aware NoteMetadata from frontmatter.
 *
 * Mapping (ADR-V6 / spec §5.3):
 * - `type`, `status`, `tags` → typed fields
 * - `createdAt` → `created`; `updatedAt` → `modified`
 * - `title`, `id`, `system`, `see_also`, `supersedes`, `superseded_by`, `deprecated`,
 *   and any other key → `properties.<lowercased>` (stringified)
 */
export function extractVaultNoteMetadata(frontmatter: string): NoteMetadata {
  const record = parseFrontmatterRecord(frontmatter);
  if (record === null) {
    return emptyVaultNoteMetadata();
  }

  const properties: Record<string, string> = {};
  for (const [key, value] of Object.entries(record)) {
    if (VAULT_TYPED_KEYS.has(key.toLowerCase())) {
      continue;
    }
    properties[key.toLowerCase()] = stringifyProperty(value);
  }

  return {
    aliases: [],
    tags: parseStringList(record.tags),
    created: toDateString(record.createdAt),
    modified: toDateString(record.updatedAt),
    source: '',
    status: typeof record.status === 'string' ? record.status : '',
    type: typeof record.type === 'string' ? record.type : '',
    base: '',
    properties,
  };
}

function emptyVaultNoteMetadata(): NoteMetadata {
  return {
    aliases: [],
    tags: [],
    created: '',
    modified: '',
    source: '',
    status: '',
    type: '',
    base: '',
    properties: {},
  };
}

function parseStringList(value: unknown): string[] {
  if (typeof value === 'string') {
    return [value];
  }
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string');
  }
  return [];
}

function stringifyProperty(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value);
}

function toDateString(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value instanceof Date) {
    return value.toISOString();
  }
  return '';
}

/**
 * Builds `recommendation` edges from frontmatter `see_also`.
 *
 * Per value: resolve against vaultRoot; when the value lacks a `.md` extension
 * and the candidate is missing, retry `value + '.md'`. Every candidate is
 * existence-gated; self-references are skipped. fs errors degrade to [].
 */
export async function buildSeeAlsoEdges(
  record: Record<string, unknown> | null,
  vaultRoot: string,
  selfPath: string,
): Promise<FileEdge[]> {
  const values = normalizeSeeAlso(record?.see_also);
  if (values.length === 0) {
    return [];
  }

  const edges: FileEdge[] = [];
  try {
    const relSelf = relativeToRoot(vaultRoot, selfPath);
    for (const value of values) {
      const candidate = await resolveExistingFile(vaultRoot, value);
      if (candidate === undefined || candidate === selfPath) {
        continue;
      }
      edges.push({
        target_path: candidate,
        relation_type: 'recommendation',
        strength: 1,
        description: `see_also from ${relSelf} to ${relativeToRoot(vaultRoot, candidate)}`,
      });
    }
  } catch {
    return [];
  }
  return edges;
}

/**
 * Resolves a wikilink target to an absolute path using the vault-specific
 * resolution ladder (spec §3.2):
 * 1. Path form (`/` in target): `resolve(vaultRoot, target + '.md')`.
 * 2. Bare form, first existing wins:
 *    a. `resolve(vaultRoot, target + '.md')` (root-level node)
 *    b. `resolve(dirname(filePath), target + '.md')` (same-folder node)
 *    c. Vault-wide stem match via lazy bounded walk (maxDepth 5, maxFiles 500):
 *       stem equals target OR starts with `target + '.'` (typed nodes).
 *       Exactly 1 match → use; 0 or >1 (ambiguous) → undefined.
 * 3. Every candidate is existence-gated; self-references and fs errors → undefined.
 */
export async function resolveWikilinkTarget(
  target: string,
  filePath: string,
  vaultRoot: string,
  selfPath: string,
): Promise<string | undefined> {
  try {
    // 1. Path form
    if (target.includes('/')) {
      const candidate = path.resolve(vaultRoot, toMd(target));
      return await pickExisting(candidate, selfPath);
    }

    // 2a. Root-level node
    const rootCandidate = path.resolve(vaultRoot, toMd(target));
    const rootHit = await pickExisting(rootCandidate, selfPath);
    if (rootHit !== undefined) {
      return rootHit;
    }

    // 2b. Same-folder node
    const sameFolderCandidate = path.resolve(path.dirname(filePath), toMd(target));
    const sameFolderHit = await pickExisting(sameFolderCandidate, selfPath);
    if (sameFolderHit !== undefined) {
      return sameFolderHit;
    }

    // 2c. Vault-wide stem match (lazy — only reached when 2a/2b miss)
    const matches = await findStemMatches(target, vaultRoot, selfPath);
    return matches.length === 1 ? matches[0] : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Builds `backlink` edges from body wikilinks using the vault resolution ladder.
 * Unresolvable targets are dropped (D49: no dangling edges).
 */
export async function buildWikilinkEdgesVault(
  wikilinks: string[],
  filePath: string,
  vaultRoot: string,
  selfPath: string,
): Promise<FileEdge[]> {
  const edges: FileEdge[] = [];
  const relSelf = relativeToRoot(vaultRoot, selfPath);
  for (const target of wikilinks) {
    const resolved = await resolveWikilinkTarget(target, filePath, vaultRoot, selfPath);
    if (resolved === undefined) {
      continue;
    }
    edges.push({
      target_path: resolved,
      relation_type: 'backlink',
      strength: 1,
      description: `wikilink from ${relSelf} to ${target}`,
    });
  }
  return edges;
}

const WIKILINK_CLEAN_REGEX = /!?\[\[([^[\]|#]+)(#[^[\]|]*)?(?:\|([^[\]]*))?\]\]/g;

/**
 * Replaces `[[target|alias]]` → `alias` and `[[target]]` → `target` in body text
 * (ADR-V5). The optional `!` embed prefix is stripped too.
 * Edge extraction runs on the ORIGINAL body; only embedding text is cleaned.
 */
export function cleanWikilinksForEmbedding(body: string): string {
  return body.replace(
    WIKILINK_CLEAN_REGEX,
    (_match, target: string, _heading: string | undefined, alias: string | undefined) =>
      alias !== undefined && alias.trim() !== '' ? alias.trim() : target.trim(),
  );
}

/**
 * Vault-aware chunker that:
 * 1. Skips index/MOC files (`_index.md`, `_Vault-Home.md`, `type: index`) → [] (ADR-V2)
 * 2. Emits see_also frontmatter relations as `recommendation` edges (ADR-V3)
 * 3. Emits body wikilinks as `backlink` edges via vault-aware resolution (ADR-V4)
 * 4. Extracts vault-aware note metadata from frontmatter (ADR-V6)
 * 5. Cleans wikilinks from the embedded body before Mastra chunking (ADR-V5)
 * 6. Reuses the established pipeline (D34) and degrades on error (D49)
 */
@Injectable()
export class VaultChunkingStrategy implements BaseChunkingStrategy {
  constructor(
    private readonly mastraChunkingService: MastraChunkingService,
    private readonly logger: BasePinoLogger,
  ) {}

  async chunkFile(
    content: string,
    filePath: string,
    sourceId: string,
    sourceConfig: WatchSourceConfig,
  ): Promise<Result<ContentChunk[]>> {
    // 1. Split frontmatter from body
    const { frontmatter, body } = splitFrontmatter(content);

    // 2. Index/MOC files are fully skipped (ADR-V2)
    if (isIndexFile(filePath, frontmatter)) {
      return Result.ok([]);
    }

    const vaultRoot = path.resolve(sourceConfig.path);
    const selfPath = path.resolve(filePath);

    // 3. see_also edges (existence-gated)
    const record = frontmatter !== null ? parseFrontmatterRecord(frontmatter) : null;
    const seeAlsoEdges = record !== null ? await buildSeeAlsoEdges(record, vaultRoot, selfPath) : [];
    const seeAlsoValues = record !== null ? normalizeSeeAlso(record.see_also) : [];

    // 4. Wikilink edges from the ORIGINAL body (vault-aware resolution ladder)
    const wikilinks = extractWikilinks(body);
    const wikilinkEdges = await buildWikilinkEdgesVault(wikilinks, filePath, vaultRoot, selfPath);

    // 5. Clean wikilinks for embedding (ADR-V5)
    const cleanedBody = cleanWikilinksForEmbedding(body);

    // 6. Vault-aware note metadata
    const noteMetadata = frontmatter !== null ? extractVaultNoteMetadata(frontmatter) : null;

    // 7. Frontmatter chunk
    const chunks: ContentChunk[] = [];
    if (frontmatter !== null && noteMetadata !== null) {
      chunks.push(this.createFrontmatterChunk(frontmatter, filePath, sourceId, noteMetadata));
    }

    // 8. Body chunks via Mastra (ko → degrade to none)
    const bodyChunksResult = await this.mastraChunkingService.chunkFile(cleanedBody, filePath, sourceId);
    const bodyChunks = bodyChunksResult.isOk() ? bodyChunksResult.getValue() : [];

    // 9. Enrich all chunks with note metadata and merge tags (clamped to TAG_LIMIT)
    const allChunks = [...chunks, ...bodyChunks];
    const enriched =
      noteMetadata !== null
        ? allChunks.map(chunk => this.enrichWithNoteMetadata(chunk, noteMetadata))
        : allChunks;

    // 10. Attach edges + note.wikilinks / note.see_also metadata when non-empty
    const edges = [...seeAlsoEdges, ...wikilinkEdges];
    const hasRelations = edges.length > 0 || wikilinks.length > 0 || seeAlsoValues.length > 0;
    const withRelations = hasRelations
      ? enriched.map(chunk => this.attachRelations(chunk, edges, wikilinks, seeAlsoValues))
      : enriched;

    // 11. D41: the strategy composes the final chunk list — re-index densely 0..m-1
    const finalChunks = withRelations.map((chunk, idx) =>
      ContentChunk.of({
        ...chunk.toJson(),
        chunkIndex: idx,
        totalChunks: withRelations.length,
      }).getValue(),
    );

    return Result.ok(finalChunks);
  }

  private createFrontmatterChunk(
    frontmatter: string,
    filePath: string,
    sourceId: string,
    noteMetadata: NoteMetadata,
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
        ...formatNoteMetadata(noteMetadata),
      },
      importance: 0.9,
      tags: ['frontmatter', 'metadata', 'vault-node', ...noteMetadata.tags].slice(0, TAG_LIMIT),
      memoryBank: 'default',
    }).getValue();
  }

  private enrichWithNoteMetadata(chunk: ContentChunk, noteMetadata: NoteMetadata): ContentChunk {
    const existingMeta = chunk.metadata ?? {};
    const enrichedMeta = {
      ...existingMeta,
      ...formatNoteMetadata(noteMetadata),
    };

    const existingTags = chunk.tags ?? [];
    const mergedTags = [...new Set([...existingTags, ...noteMetadata.tags])].slice(0, TAG_LIMIT);

    return ContentChunk.of({
      ...chunk.toJson(),
      metadata: enrichedMeta,
      tags: mergedTags,
    }).getValue();
  }

  private attachRelations(
    chunk: ContentChunk,
    edges: FileEdge[],
    wikilinks: string[],
    seeAlsoValues: string[],
  ): ContentChunk {
    const existingMeta = chunk.metadata ?? {};
    const metadata: Record<string, string> = { ...existingMeta };
    if (wikilinks.length > 0) {
      metadata['note.wikilinks'] = JSON.stringify(wikilinks);
    }
    if (seeAlsoValues.length > 0) {
      metadata['note.see_also'] = JSON.stringify(seeAlsoValues);
    }

    return ContentChunk.of({
      ...chunk.toJson(),
      metadata,
      ...(edges.length > 0 && { edges }),
    }).getValue();
  }
}

// --- Internal helpers (private to the strategy; tested via exported API) ---

function normalizeSeeAlso(value: unknown): string[] {
  if (typeof value === 'string') {
    return value.trim() !== '' ? [value] : [];
  }
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string');
  }
  return [];
}

async function isFile(candidate: string): Promise<boolean> {
  try {
    const stats = await fsp.stat(candidate);
    return stats.isFile();
  } catch {
    return false;
  }
}

async function resolveExistingFile(vaultRoot: string, value: string): Promise<string | undefined> {
  const candidate = path.resolve(vaultRoot, value);
  if (await isFile(candidate)) {
    return candidate;
  }
  if (path.extname(candidate) === '.md') {
    return undefined;
  }
  const retried = path.resolve(vaultRoot, `${value}.md`);
  return (await isFile(retried)) ? retried : undefined;
}

function toMd(target: string): string {
  return target.endsWith('.md') ? target : `${target}.md`;
}

async function pickExisting(candidate: string, selfPath: string): Promise<string | undefined> {
  if (!(await isFile(candidate))) {
    return undefined;
  }
  if (candidate === selfPath) {
    return undefined;
  }
  return candidate;
}

async function findStemMatches(target: string, vaultRoot: string, selfPath: string): Promise<string[]> {
  const matches: string[] = [];
  const typedPrefix = `${target}.`;
  let visitedMdFiles = 0;
  const queue: { dir: string; depth: number }[] = [{ dir: vaultRoot, depth: 0 }];

  while (queue.length > 0 && matches.length < 2) {
    const { dir, depth } = queue.shift()!;

    let entries: import('fs').Dirent[];
    try {
      entries = await fsp.readdir(dir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (depth + 1 <= MAX_WALK_DEPTH) {
          queue.push({ dir: fullPath, depth: depth + 1 });
        }
        continue;
      }
      if (!entry.isFile() || !entry.name.endsWith('.md')) {
        continue;
      }
      visitedMdFiles += 1;
      if (visitedMdFiles > MAX_WALK_FILES) {
        return matches;
      }
      const stem = entry.name.slice(0, -3);
      if ((stem === target || stem.startsWith(typedPrefix)) && fullPath !== selfPath) {
        matches.push(fullPath);
      }
    }
  }

  return matches;
}

function relativeToRoot(vaultRoot: string, absolutePath: string): string {
  const rel = path.relative(vaultRoot, absolutePath);
  return rel !== '' ? rel : path.basename(absolutePath);
}
