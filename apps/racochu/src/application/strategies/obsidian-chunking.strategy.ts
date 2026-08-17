import { Injectable } from '@nestjs/common';
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

/** Typed frontmatter keys that map to explicit NoteMetadata fields. */
const TYPED_KEYS = new Set(['aliases', 'tags', 'created', 'modified', 'source', 'status', 'type', 'base']);

/**
 * Parses YAML frontmatter string into NoteMetadata.
 * Typed keys (aliases, tags, created, modified, source, status, type, base)
 * go to their explicit fields. All remaining keys are collected into
 * `properties` with lowercased keys and stringified values.
 */
export function extractNoteMetadata(frontmatter: string): NoteMetadata {
  try {
    const parsed = yaml.load(frontmatter) as Record<string, unknown> | null;
    if (!parsed || typeof parsed !== 'object') {
      return emptyNoteMetadata();
    }

    const properties: Record<string, string> = {};

    for (const [key, value] of Object.entries(parsed)) {
      const lowerKey = key.toLowerCase();
      if (TYPED_KEYS.has(lowerKey)) continue;

      properties[lowerKey] = typeof value === 'string' ? value : JSON.stringify(value);
    }

    return {
      aliases: parseStringArray(parsed.aliases),
      tags: parseStringArray(parsed.tags),
      created: typeof parsed.created === 'string' ? parsed.created : '',
      modified: typeof parsed.modified === 'string' ? parsed.modified : '',
      source: typeof parsed.source === 'string' ? parsed.source : '',
      status: typeof parsed.status === 'string' ? parsed.status : '',
      type: typeof parsed.type === 'string' ? parsed.type : '',
      base: typeof parsed.base === 'string' ? parsed.base : '',
      properties,
    };
  } catch {
    return emptyNoteMetadata();
  }
}

function parseStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string');
  }
  if (typeof value === 'string') {
    return [value];
  }
  return [];
}

function emptyNoteMetadata(): NoteMetadata {
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

function formatNoteMetadata(metadata: NoteMetadata): Record<string, string> {
  const result: Record<string, string> = {
    'note.aliases': JSON.stringify(metadata.aliases),
    'note.tags': JSON.stringify(metadata.tags),
    'note.created': metadata.created,
    'note.modified': metadata.modified,
    'note.source': metadata.source,
    'note.status': metadata.status,
    'note.type': metadata.type,
    'note.base': metadata.base,
  };

  for (const [key, value] of Object.entries(metadata.properties)) {
    result[`note.properties.${key}`] = value;
  }

  return result;
}

/**
 * Resolves deduplicated wikilink targets to backlink edges against the watch-source root.
 * - `[[Note]]` → `<root>/Note.md`
 * - `[[Note|alias]]` / `[[Note#heading]]` → target before `|`, `#heading` stripped
 *   (already normalized by extractWikilinks)
 * - `[[sub/Note]]` → `<root>/sub/Note.md`
 * Unresolvable targets still yield a best-effort edge (bensyne stub policy D4).
 */
export function buildWikilinkEdges(
  wikilinks: string[],
  vaultRoot: string,
  sourceNoteName: string,
): FileEdge[] {
  return wikilinks.map(target => ({
    target_path: path.join(vaultRoot, `${target}.md`),
    relation_type: 'backlink',
    strength: 1,
    description: `wikilink from ${sourceNoteName} to ${target}`,
  }));
}

/**
 * Obsidian-aware chunking strategy that:
 * 1. Splits frontmatter from body using shared splitFrontmatter
 * 2. Extracts note metadata (aliases, tags, etc.) from frontmatter via js-yaml
 * 3. Creates frontmatter chunk with high importance (0.9) and obsidian-note tags
 * 4. Chunks body via MastraChunkingService
 * 5. Enriches all chunks with note metadata and merges note tags into chunk tags
 */
@Injectable()
export class ObsidianChunkingStrategy implements BaseChunkingStrategy {
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

    // 2. Extract wikilinks from body (body-derived, independent of frontmatter)
    const wikilinks = extractWikilinks(body);

    // 3. Resolve wikilinks to backlink edges against the watch-source root
    const sourceNoteName = path.basename(filePath).replace(/\.md$/i, '');
    const edges = buildWikilinkEdges(wikilinks, sourceConfig.path, sourceNoteName);

    // 4. Extract note metadata if frontmatter exists
    const noteMetadata = frontmatter ? extractNoteMetadata(frontmatter) : null;

    // 5. Create frontmatter chunk if present
    const chunks: ContentChunk[] = [];
    if (frontmatter !== null) {
      // noteMetadata is non-null here because frontmatter exists
      chunks.push(this.createFrontmatterChunk(frontmatter, filePath, sourceId, noteMetadata!));
    }

    // 6. Chunk body with Mastra
    const bodyChunksResult = await this.mastraChunkingService.chunkFile(body, filePath, sourceId);
    const bodyChunks = bodyChunksResult.isOk() ? bodyChunksResult.getValue() : [];

    // 7. Enrich all chunks with note metadata and merge tags
    const allChunks = [...chunks, ...bodyChunks];
    const enriched = noteMetadata
      ? allChunks.map(chunk => this.enrichWithNoteMetadata(chunk, noteMetadata))
      : allChunks;

    // 8. Attach wikilinks (legacy key) + resolved edges to all chunks (only when non-empty)
    const withWikilinks =
      wikilinks.length > 0
        ? enriched.map(chunk => this.attachWikilinksAndEdges(chunk, wikilinks, edges))
        : enriched;

    return Result.ok(withWikilinks);
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
      tags: ['frontmatter', 'metadata', 'obsidian-note', ...noteMetadata.tags],
      memoryBank: 'default',
    }).getValue();
  }

  private enrichWithNoteMetadata(chunk: ContentChunk, noteMetadata: NoteMetadata): ContentChunk {
    const existingMeta = chunk.metadata ?? {};
    const enrichedMeta = {
      ...existingMeta,
      ...formatNoteMetadata(noteMetadata),
    };

    // Merge note tags into chunk tags, avoiding duplicates
    const existingTags = chunk.tags ?? [];
    const mergedTags = [...new Set([...existingTags, ...noteMetadata.tags])];

    return ContentChunk.of({
      ...chunk.toJson(),
      metadata: enrichedMeta,
      tags: mergedTags,
    }).getValue();
  }

  private attachWikilinksAndEdges(chunk: ContentChunk, wikilinks: string[], edges: FileEdge[]): ContentChunk {
    const existingMeta = chunk.metadata ?? {};
    const withWikilinks = {
      ...existingMeta,
      'note.wikilinks': JSON.stringify(wikilinks),
    };

    return ContentChunk.of({
      ...chunk.toJson(),
      metadata: withWikilinks,
      edges,
    }).getValue();
  }
}
