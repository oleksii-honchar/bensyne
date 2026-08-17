import { FILE_ROLES } from '@/domain/content-chunk.entity';
import { aBodyChunk } from '@/domain/content-chunk.entity.test-utils';
import { NoteMetadata } from '@/domain/note-metadata.type';
import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import '@/utils/mastra-rag.test-utils';
import { splitFrontmatter } from '@/utils/strategy-utils';
import * as fsSync from 'fs';
import * as path from 'path';
import { MastraChunkingService } from './mastra-chunking.service';
import { aMastraChunkingService } from './mastra-chunking.service.test-utils';
import { ObsidianChunkingStrategy, extractNoteMetadata } from './obsidian-chunking.strategy';

// --- Test fixtures (loaded from shared fixtures) ---

const WITH_FRONTMATTER = fsSync.readFileSync(
  path.resolve(__dirname, '../../e2e/fixtures/obsidian-with-frontmatter.md'),
  'utf-8',
);

const WITHOUT_FRONTMATTER = fsSync.readFileSync(
  path.resolve(__dirname, '../../e2e/fixtures/obsidian-without-frontmatter.md'),
  'utf-8',
);

const EMPTY_FRONTMATTER = fsSync.readFileSync(
  path.resolve(__dirname, '../../e2e/fixtures/obsidian-empty-frontmatter.md'),
  'utf-8',
);

const WITH_WIKILINKS = fsSync.readFileSync(
  path.resolve(__dirname, '../../e2e/fixtures/obsidian-with-wikilinks.md'),
  'utf-8',
);

const TEST_NOTE_META: NoteMetadata = {
  aliases: [],
  tags: ['notes'],
  created: '',
  modified: '',
  source: '',
  status: '',
  type: '',
  base: '[[My Brand Notes.base]]',
  properties: {
    'notion-id': '6f6f0482-ba1c-4ce7-8f6d-a5b3b03982d8',
    kind: 'note',
    project: 'my-brand',
  },
};

// --- Tests ---

describe('extractNoteMetadata', () => {
  it('extracts all fields from valid frontmatter', () => {
    const { frontmatter } = splitFrontmatter(WITH_FRONTMATTER);
    const result = extractNoteMetadata(frontmatter!);

    expect(result.aliases).toEqual([]);
    expect(result.tags).toEqual(['notes']);
    expect(result.created).toBe('');
    expect(result.modified).toBe('');
    expect(result.source).toBe('');
    expect(result.status).toBe('');
    expect(result.type).toBe('');
    expect(result.base).toBe('[[My Brand Notes.base]]');
    expect(result.properties).toEqual({
      'notion-id': '6f6f0482-ba1c-4ce7-8f6d-a5b3b03982d8',
      kind: 'note',
      project: 'my-brand',
    });
  });

  it('returns defaults for missing fields', () => {
    const partialFrontmatter = `created: 2026-01-01
status: draft`;
    const result = extractNoteMetadata(partialFrontmatter);

    expect(result.aliases).toEqual([]);
    expect(result.tags).toEqual([]);
    expect(result.created).toBe('2026-01-01');
    expect(result.modified).toBe('');
    expect(result.source).toBe('');
    expect(result.status).toBe('draft');
    expect(result.type).toBe('');
    expect(result.base).toBe('');
    expect(result.properties).toEqual({});
  });

  it('returns all defaults for empty frontmatter', () => {
    const result = extractNoteMetadata('');

    expect(result.aliases).toEqual([]);
    expect(result.tags).toEqual([]);
    expect(result.created).toBe('');
    expect(result.modified).toBe('');
    expect(result.source).toBe('');
    expect(result.status).toBe('');
    expect(result.type).toBe('');
    expect(result.base).toBe('');
    expect(result.properties).toEqual({});
  });

  it('handles invalid YAML gracefully', () => {
    const result = extractNoteMetadata('::: invalid yaml {{{');

    expect(result.aliases).toEqual([]);
    expect(result.tags).toEqual([]);
    expect(result.created).toBe('');
    expect(result.modified).toBe('');
    expect(result.source).toBe('');
    expect(result.status).toBe('');
    expect(result.type).toBe('');
    expect(result.base).toBe('');
    // js-yaml parses "::: invalid yaml {{{" as {"::": "invalid yaml {{{"}
    // which is not a typed key, so it ends up in properties
    expect(result.properties).toEqual({ '::': 'invalid yaml {{{' });
  });

  it('handles aliases as a single string (not array)', () => {
    const frontmatter = `aliases: Single Alias
tags: single-tag`;
    const result = extractNoteMetadata(frontmatter);

    expect(result.aliases).toEqual(['Single Alias']);
    expect(result.tags).toEqual(['single-tag']);
  });

  it('handles tags as a single string (not array)', () => {
    const frontmatter = `tags: single-tag`;
    const result = extractNoteMetadata(frontmatter);

    expect(result.tags).toEqual(['single-tag']);
  });

  it('extracts generic properties with lowercased keys', () => {
    const frontmatter = `notion-id: abc-123
Kind: note
Project: my-brand`;
    const result = extractNoteMetadata(frontmatter);

    expect(result.properties).toEqual({
      'notion-id': 'abc-123',
      kind: 'note',
      project: 'my-brand',
    });
  });

  it('lowercases capitalized keys in properties', () => {
    const frontmatter = `Kind: note`;
    const result = extractNoteMetadata(frontmatter);

    expect(result.properties.kind).toBe('note');
    expect(Object.keys(result.properties)).not.toContain('Kind');
  });

  it('extracts base field from frontmatter', () => {
    const frontmatter = `base: "[[My Brand Notes.base]]"`;
    const result = extractNoteMetadata(frontmatter);

    expect(result.base).toBe('[[My Brand Notes.base]]');
  });

  it('stringifies non-string property values with JSON.stringify', () => {
    const frontmatter = `array-field:
  - 1
  - 2
number-field: 42`;
    const result = extractNoteMetadata(frontmatter);

    expect(result.properties['array-field']).toBe(JSON.stringify([1, 2]));
    expect(result.properties['number-field']).toBe(JSON.stringify(42));
  });

  it('excludes typed keys from properties', () => {
    const frontmatter = `tags:
  - tag1
created: 2026-01-01
custom-key: custom-value`;
    const result = extractNoteMetadata(frontmatter);

    expect(result.tags).toEqual(['tag1']);
    expect(result.created).toBe('2026-01-01');
    expect(result.properties).not.toHaveProperty('tags');
    expect(result.properties).not.toHaveProperty('created');
    expect(result.properties).toHaveProperty('custom-key', 'custom-value');
  });

  it('excludes capitalized typed keys from properties (casing issue fix)', () => {
    const frontmatter = `Tags:
  - tag1
Created: 2026-01-01
Aliases:
  - alias1
Custom-key: custom-value`;
    const result = extractNoteMetadata(frontmatter);

    // Capitalized typed keys must NOT leak into properties
    expect(result.properties).not.toHaveProperty('tags');
    expect(result.properties).not.toHaveProperty('created');
    expect(result.properties).not.toHaveProperty('aliases');
    expect(result.properties).toHaveProperty('custom-key', 'custom-value');
  });
});

describe('ObsidianChunkingStrategy', () => {
  let strategy: ObsidianChunkingStrategy;
  let mockMastraChunkingService: ReturnType<typeof aMastraChunkingService>;
  let mockLogger: BasePinoLogger;

  beforeEach(() => {
    jest.clearAllMocks();
    mockMastraChunkingService = aMastraChunkingService();
    mockLogger = aLogger();
    strategy = new ObsidianChunkingStrategy(
      mockMastraChunkingService as unknown as MastraChunkingService,
      mockLogger,
    );
  });

  describe('implements ChunkingStrategy', () => {
    it('has chunkFile method with correct signature', () => {
      expect(typeof strategy.chunkFile).toBe('function');
    });
  });

  describe('chunkFile with frontmatter', () => {
    it('creates frontmatter chunk with importance 0.9, correct tags and sectionHeader', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBe(2);

      const fmChunk = chunks[0];
      expect(fmChunk.importance).toBe(0.9);
      expect(fmChunk.tags).toContain('frontmatter');
      expect(fmChunk.tags).toContain('metadata');
      expect(fmChunk.tags).toContain('obsidian-note');
      expect(fmChunk.sectionHeader).toBe('Frontmatter');
      expect(fmChunk.text).toContain('---');
      expect(fmChunk.text).toContain('---');
      expect(fmChunk.fileRole).toBe(FILE_ROLES.DOCS);
    });

    it('wraps frontmatter chunk text in --- delimiters', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      const fmChunk = result.getValue()[0];
      expect(fmChunk.text).toMatch(/^---\n[\s\S]*\n---$/);
    });

    it('passes body content (not full content) to MastraChunkingService', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      const expectedBody = splitFrontmatter(WITH_FRONTMATTER).body;
      expect(mockMastraChunkingService.chunkFile).toHaveBeenCalledWith(
        expectedBody,
        '/test/path/note.md',
        'test-source',
      );
    });

    it('enriches all chunks with note metadata', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      const chunks = result.getValue();

      // Frontmatter chunk metadata (from real fixture)
      const fmMeta = chunks[0].metadata;
      expect(fmMeta?.['note.aliases']).toBe(JSON.stringify(TEST_NOTE_META.aliases));
      expect(fmMeta?.['note.tags']).toBe(JSON.stringify(TEST_NOTE_META.tags));
      expect(fmMeta?.['note.created']).toBe('');
      expect(fmMeta?.['note.modified']).toBe('');
      expect(fmMeta?.['note.source']).toBe('');
      expect(fmMeta?.['note.status']).toBe('');
      expect(fmMeta?.['note.type']).toBe('');
      expect(fmMeta?.['note.base']).toBe('[[My Brand Notes.base]]');
      expect(fmMeta?.['note.properties.notion-id']).toBe('6f6f0482-ba1c-4ce7-8f6d-a5b3b03982d8');
      expect(fmMeta?.['note.properties.kind']).toBe('note');
      expect(fmMeta?.['note.properties.project']).toBe('my-brand');

      // Body chunk metadata (from real fixture)
      const bodyMeta = chunks[1].metadata;
      expect(bodyMeta?.['note.aliases']).toBe(JSON.stringify(TEST_NOTE_META.aliases));
      expect(bodyMeta?.['note.tags']).toBe(JSON.stringify(TEST_NOTE_META.tags));
      expect(bodyMeta?.['note.created']).toBe('');
      expect(bodyMeta?.['note.modified']).toBe('');
      expect(bodyMeta?.['note.source']).toBe('');
      expect(bodyMeta?.['note.status']).toBe('');
      expect(bodyMeta?.['note.type']).toBe('');
      expect(bodyMeta?.['note.base']).toBe('[[My Brand Notes.base]]');
      expect(bodyMeta?.['note.properties.notion-id']).toBe('6f6f0482-ba1c-4ce7-8f6d-a5b3b03982d8');
      expect(bodyMeta?.['note.properties.kind']).toBe('note');
      expect(bodyMeta?.['note.properties.project']).toBe('my-brand');
    });

    it('merges note tags into chunk tags', async () => {
      const bodyChunk = aBodyChunk({ tags: ['existing-tag'] });
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      const chunks = result.getValue();

      // Frontmatter chunk should have note tags (from real fixture: only 'notes')
      const fmTags = chunks[0].tags;
      expect(fmTags).toContain('notes');

      // Body chunk should have both existing and note tags (from real fixture: only 'notes')
      const bodyTags = chunks[1].tags;
      expect(bodyTags).toContain('existing-tag');
      expect(bodyTags).toContain('notes');
    });

    it('returns multiple body chunks from Mastra with enrichment', async () => {
      const chunk1 = aBodyChunk({ chunkIndex: 0 });
      const chunk2 = aBodyChunk({ chunkIndex: 1 });
      mockMastraChunkingService = aMastraChunkingService([chunk1, chunk2]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      // 1 frontmatter + 2 body chunks
      expect(chunks.length).toBe(3);

      // All body chunks should be enriched (real fixture has no 'created' field)
      for (let i = 1; i < chunks.length; i++) {
        expect(chunks[i].metadata?.['note.created']).toBe('');
        expect(chunks[i].tags).toContain('notes');
      }
    });
  });

  describe('chunkFile without frontmatter', () => {
    it('skips frontmatter chunk and returns only body chunks', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITHOUT_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBe(1);
      expect(chunks[0].sectionHeader).not.toBe('Frontmatter');
    });

    it('passes full content to Mastra when no frontmatter', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await strategy.chunkFile(
        WITHOUT_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(mockMastraChunkingService.chunkFile).toHaveBeenCalledWith(
        WITHOUT_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
      );
    });

    it('does not enrich chunks with note metadata when no frontmatter', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITHOUT_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      const chunks = result.getValue();
      expect(chunks[0].metadata?.['note.aliases']).toBeUndefined();
      expect(chunks[0].metadata?.['note.tags']).toBeUndefined();
      expect(chunks[0].metadata?.['note.created']).toBeUndefined();
      expect(chunks[0].metadata?.['note.base']).toBeUndefined();
      expect(chunks[0].metadata?.['note.properties.notion-id']).toBeUndefined();
    });
  });

  describe('chunkFile with empty frontmatter', () => {
    it('treats ---\\n--- as no frontmatter (regex requires content between delimiters)', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        EMPTY_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      // Empty frontmatter (---\n---) is not matched by the regex, so treated as no frontmatter
      expect(chunks.length).toBe(1);
      expect(chunks[0].sectionHeader).not.toBe('Frontmatter');
    });
  });

  describe('body chunking via Mastra', () => {
    it('delegates body chunking to MastraChunkingService', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(mockMastraChunkingService.chunkFile).toHaveBeenCalledTimes(1);
    });
  });

  describe('empty content', () => {
    it('returns empty array for empty content', async () => {
      mockMastraChunkingService = aMastraChunkingService([]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        '',
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual([]);
    });
  });

  describe('wikilink wiring', () => {
    const contentWithWikilinks = `---
tags:
  - notes
---
This note links to [[Note A]] and [[Note B|alias]].
Also references [[Note C#Section]] and ![[Note D]].
Duplicate: [[Note A]] again.`;

    const contentWithWikilinksNoFrontmatter = `This note links to [[Note A]] and [[Note B]].`;

    const contentWithoutWikilinks = `---
tags:
  - notes
---
Plain text with no wikilinks here.`;

    it('attaches note.wikilinks to frontmatter chunk when wikilinks present', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        contentWithWikilinks,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      const fmChunk = chunks[0];

      expect(fmChunk.metadata?.['note.wikilinks']).toBeDefined();
      const wikilinks = JSON.parse(fmChunk.metadata!['note.wikilinks']);
      expect(wikilinks).toContain('Note A');
      expect(wikilinks).toContain('Note B');
      expect(wikilinks).toContain('Note C');
      expect(wikilinks).toContain('Note D');
    });

    it('attaches note.wikilinks to body chunks when wikilinks present', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        contentWithWikilinks,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      const bodyChunkResult = chunks[1];

      expect(bodyChunkResult.metadata?.['note.wikilinks']).toBeDefined();
      const wikilinks = JSON.parse(bodyChunkResult.metadata!['note.wikilinks']);
      expect(wikilinks).toContain('Note A');
      expect(wikilinks).toContain('Note B');
    });

    it('deduplicates wikilinks', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        contentWithWikilinks,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      const wikilinks = JSON.parse(chunks[0].metadata!['note.wikilinks']);

      // Note A appears twice in source but should only appear once
      expect(wikilinks.filter((w: string) => w === 'Note A').length).toBe(1);
    });

    it('attaches wikilinks to body chunks when no frontmatter', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        contentWithWikilinksNoFrontmatter,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBe(1);

      expect(chunks[0].metadata?.['note.wikilinks']).toBeDefined();
      const wikilinks = JSON.parse(chunks[0].metadata!['note.wikilinks']);
      expect(wikilinks).toContain('Note A');
      expect(wikilinks).toContain('Note B');
    });

    it('omits note.wikilinks key when no wikilinks present', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        contentWithoutWikilinks,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();

      // Neither frontmatter nor body chunk should have note.wikilinks
      expect(chunks[0].metadata?.['note.wikilinks']).toBeUndefined();
      expect(chunks[1].metadata?.['note.wikilinks']).toBeUndefined();
    });

    it('no regression: frontmatter enrichment and tag merging still work with wikilinks', async () => {
      const bodyChunk = aBodyChunk({ tags: ['existing-tag'] });
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        contentWithWikilinks,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();

      // Frontmatter chunk: note metadata + wikilinks
      const fmMeta = chunks[0].metadata;
      expect(fmMeta?.['note.tags']).toBe(JSON.stringify(['notes']));
      expect(fmMeta?.['note.wikilinks']).toBeDefined();

      // Body chunk: merged tags + wikilinks
      const bodyTags = chunks[1].tags;
      expect(bodyTags).toContain('existing-tag');
      expect(bodyTags).toContain('notes');
      expect(chunks[1].metadata?.['note.wikilinks']).toBeDefined();
    });

    it('wikilinks attached to all chunks using obsidian-with-wikilinks fixture', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_WIKILINKS,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      // 1 frontmatter + 1 body chunk
      expect(chunks.length).toBe(2);

      // Frontmatter chunk has note.wikilinks
      const fmWikilinks = JSON.parse(chunks[0].metadata!['note.wikilinks']);
      expect(fmWikilinks).toContain('Acme Platform');
      expect(fmWikilinks).toContain('Design System');
      expect(fmWikilinks).toContain('Technical Requirements');
      expect(fmWikilinks).toContain('CI/CD Pipeline');
      expect(fmWikilinks).toContain('Sarah Chen');
      expect(fmWikilinks).toContain('API Gateway');
      expect(fmWikilinks).toContain('Note A');
      expect(fmWikilinks).toContain('Note B');
      expect(fmWikilinks).toContain('Note C');
      expect(fmWikilinks).toContain('Note D');
      expect(fmWikilinks).toContain('Note E');

      // Body chunk also has note.wikilinks
      const bodyWikilinks = JSON.parse(chunks[1].metadata!['note.wikilinks']);
      expect(bodyWikilinks).toContain('Acme Platform');
      expect(bodyWikilinks).toContain('Design System');
      expect(bodyWikilinks).toContain('Note A');
      expect(bodyWikilinks).toContain('Note B');
    });

    it('wikilinks deduped — duplicate link in fixture produces single entry', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_WIKILINKS,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      const wikilinks = JSON.parse(chunks[0].metadata!['note.wikilinks']);

      // Note A appears 3 times in the fixture but should only appear once
      expect(wikilinks.filter((w: string) => w === 'Note A').length).toBe(1);
      // Note B appears twice in the fixture but should only appear once
      expect(wikilinks.filter((w: string) => w === 'Note B').length).toBe(1);
    });

    it('wikilinks attached when no frontmatter — body chunks get note.wikilinks', async () => {
      const contentWithoutFmWithLinks = `This note links to [[Note A]] and [[Note B]].`;
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        contentWithoutFmWithLinks,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBe(1);
      expect(chunks[0].sectionHeader).not.toBe('Frontmatter');

      expect(chunks[0].metadata?.['note.wikilinks']).toBeDefined();
      const wikilinks = JSON.parse(chunks[0].metadata!['note.wikilinks']);
      expect(wikilinks).toContain('Note A');
      expect(wikilinks).toContain('Note B');
    });

    it('no note.wikilinks key when no links present — backward compatible', async () => {
      const contentWithoutLinks = `---
tags:
  - notes
---
Plain text with no wikilinks here.`;
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        contentWithoutLinks,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.['note.wikilinks']).toBeUndefined();
      expect(chunks[1].metadata?.['note.wikilinks']).toBeUndefined();
    });

    // --- Wikilink → edges resolution (unified chunk contract v1) ---

    const VAULT_ROOT = '/vault';

    const vaultConfig = aWatchSourceConfig({
      id: 'test-source',
      path: VAULT_ROOT,
      memoryBank: 'test-source',
      exclude: ['**/node_modules/**'],
      strategy: 'obsidian',
    });

    function chunkWith(content: string, filePath = '/vault/note-a.md') {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );
      return strategy.chunkFile(content, filePath, 'test-source', vaultConfig);
    }

    it('resolves [[Note B]] to <root>/Note B.md backlink edge (exact object)', async () => {
      const result = await chunkWith('This note links to [[Note B]].');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      for (const chunk of chunks) {
        expect(chunk.edges).toEqual([
          {
            target_path: '/vault/Note B.md',
            relation_type: 'backlink',
            strength: 1,
            description: 'wikilink from note-a to Note B',
          },
        ]);
      }
    });

    it('resolves [[Note|alias]] to target before the pipe', async () => {
      const result = await chunkWith('Link with alias: [[Target Note|some alias]].');

      expect(result.isOk()).toBe(true);
      const edges = result.getValue()[0].edges;
      expect(edges).toEqual([
        {
          target_path: '/vault/Target Note.md',
          relation_type: 'backlink',
          strength: 1,
          description: 'wikilink from note-a to Target Note',
        },
      ]);
    });

    it('resolves [[Note#heading]] by stripping the heading fragment', async () => {
      const result = await chunkWith('Link with heading: [[Target Note#Section]].');

      expect(result.isOk()).toBe(true);
      const edges = result.getValue()[0].edges;
      expect(edges).toEqual([
        {
          target_path: '/vault/Target Note.md',
          relation_type: 'backlink',
          strength: 1,
          description: 'wikilink from note-a to Target Note',
        },
      ]);
    });

    it('resolves [[sub/Note]] relative path to <root>/sub/Note.md', async () => {
      const result = await chunkWith('Relative link: [[sub/Note]].');

      expect(result.isOk()).toBe(true);
      const edges = result.getValue()[0].edges;
      expect(edges).toEqual([
        {
          target_path: '/vault/sub/Note.md',
          relation_type: 'backlink',
          strength: 1,
          description: 'wikilink from note-a to sub/Note',
        },
      ]);
    });

    it('emits one edge per wikilink and de-duplicates repeated links (exact count)', async () => {
      const content =
        'Links: [[Alpha]] and [[Beta|b]] and [[Gamma#h]]. Duplicates: [[Alpha]] again, [[Beta|x]].';
      const result = await chunkWith(content);

      expect(result.isOk()).toBe(true);
      for (const chunk of result.getValue()) {
        expect(chunk.edges).toHaveLength(3);
        expect(chunk.edges?.map(e => e.target_path)).toEqual([
          '/vault/Alpha.md',
          '/vault/Beta.md',
          '/vault/Gamma.md',
        ]);
      }
    });

    it('emits edge with best-effort path for unresolvable target without throwing', async () => {
      const result = await chunkWith('Dangling link: [[missing note]].');

      expect(result.isOk()).toBe(true);
      const edges = result.getValue()[0].edges;
      expect(edges).toEqual([
        {
          target_path: '/vault/missing note.md',
          relation_type: 'backlink',
          strength: 1,
          description: 'wikilink from note-a to missing note',
        },
      ]);
    });

    it('keeps legacy note.wikilinks metadata alongside new edges', async () => {
      const result = await chunkWith('Links: [[Note A]] and [[Note B]].');

      expect(result.isOk()).toBe(true);
      for (const chunk of result.getValue()) {
        expect(chunk.metadata?.['note.wikilinks']).toBeDefined();
        const wikilinks = JSON.parse(chunk.metadata!['note.wikilinks']);
        expect(wikilinks).toEqual(['Note A', 'Note B']);
        expect(chunk.edges).toHaveLength(2);
      }
    });

    it('emits no edges for a note with no wikilinks (behavior identical to today)', async () => {
      const result = await chunkWith('Plain text, no links here.');

      expect(result.isOk()).toBe(true);
      for (const chunk of result.getValue()) {
        expect(chunk.edges).toBeUndefined();
        expect(chunk.metadata?.['note.wikilinks']).toBeUndefined();
      }
    });

    it('obsidian-with-wikilinks fixture: all chunks get note.base and note.properties.*', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);
      strategy = new ObsidianChunkingStrategy(
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_WIKILINKS,
        '/test/path/note.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'obsidian',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();

      // Both chunks should have note.base
      expect(chunks[0].metadata?.['note.base']).toBe('[[Project Notes.base]]');
      expect(chunks[1].metadata?.['note.base']).toBe('[[Project Notes.base]]');

      // Both chunks should have note.properties.*
      expect(chunks[0].metadata?.['note.properties.notion-id']).toBe('a1b2c3d4-e5f6-7890-abcd-ef1234567890');
      expect(chunks[0].metadata?.['note.properties.kind']).toBe('note');
      expect(chunks[0].metadata?.['note.properties.project']).toBe('acme-platform');

      expect(chunks[1].metadata?.['note.properties.notion-id']).toBe('a1b2c3d4-e5f6-7890-abcd-ef1234567890');
      expect(chunks[1].metadata?.['note.properties.kind']).toBe('note');
      expect(chunks[1].metadata?.['note.properties.project']).toBe('acme-platform');
    });
  });
});
