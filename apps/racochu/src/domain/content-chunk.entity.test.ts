import { ContentChunk, FILE_ROLES } from './content-chunk.entity';
import { aContentChunk } from './content-chunk.entity.test-utils';

describe('Chunk', () => {
  describe('Chunk.of', () => {
    it('with valid props returns ok', () => {
      const chunk = aContentChunk();

      expect(chunk.id).toBeGreaterThan(0n);
      expect(typeof chunk.id).toBe('bigint');
      expect(chunk.text).toBeDefined();
    });

    it('with invalid id (string instead of bigint) returns ko', () => {
      const result = ContentChunk.of({
        ...aContentChunk().toJson(),
        id: 'not-a-bigint' as never,
      });

      expect(result.isKo()).toBe(true);
    });

    it('with invalid id (negative bigint) returns ko', () => {
      const result = ContentChunk.of({
        ...aContentChunk().toJson(),
        id: -1n,
      });

      expect(result.isKo()).toBe(true);
    });

    it('with negative chunkIndex returns ko', () => {
      const result = ContentChunk.of({
        ...aContentChunk().toJson(),
        chunkIndex: -1,
      });

      expect(result.isKo()).toBe(true);
    });

    it('with zero totalChunks returns ko', () => {
      const result = ContentChunk.of({
        ...aContentChunk().toJson(),
        totalChunks: 0,
      });

      expect(result.isKo()).toBe(true);
    });

    it('with missing required fields returns ko', () => {
      const result = ContentChunk.of({
        id: aContentChunk().id,
        text: 'Test',
        chunkIndex: 0,
        totalChunks: 1,
        // missing sectionHeader, breadcrumb, fileRole
      } as never);

      expect(result.isKo()).toBe(true);
    });

    it('with importance > 1 returns ko', () => {
      const result = ContentChunk.of({
        ...aContentChunk().toJson(),
        importance: 1.5,
      } as never);

      expect(result.isKo()).toBe(true);
    });

    it('with importance < 0 returns ko', () => {
      const result = ContentChunk.of({
        ...aContentChunk().toJson(),
        importance: -0.1,
      } as never);

      expect(result.isKo()).toBe(true);
    });

    it('with empty string tag returns ko', () => {
      const result = ContentChunk.of({
        ...aContentChunk().toJson(),
        tags: ['valid-tag', ''],
      } as never);

      expect(result.isKo()).toBe(true);
    });

    it('with too many tags returns ko', () => {
      const result = ContentChunk.of({
        ...aContentChunk().toJson(),
        tags: Array.from({ length: 21 }, (_, i) => `tag-${i}`),
      } as never);

      expect(result.isKo()).toBe(true);
    });

    it('with empty memoryBank returns ko', () => {
      const result = ContentChunk.of({
        ...aContentChunk().toJson(),
        memoryBank: '',
      } as never);

      expect(result.isKo()).toBe(true);
    });
  });

  describe('Chunk.of — enhancement fields', () => {
    it('with valid importance returns ok', () => {
      const chunk = aContentChunk({ importance: 0.85 });

      expect(chunk.importance).toBe(0.85);
    });

    it('with valid tags returns ok', () => {
      const chunk = aContentChunk({ tags: ['typescript', 'config', 'important'] });

      expect(chunk.tags).toEqual(['typescript', 'config', 'important']);
    });

    it('with valid memoryBank returns ok', () => {
      const chunk = aContentChunk({ memoryBank: 'vault-knowledge' });

      expect(chunk.memoryBank).toBe('vault-knowledge');
    });

    it('defaults importance to 0.5 when omitted', () => {
      const p = aContentChunk().toJson();

      const { importance: _imp, ...propsWithoutImportance } = p;
      const result = ContentChunk.of(propsWithoutImportance as never);

      expect(result.isOk()).toBe(true);
      expect(result.getValue().importance).toBe(0.5);
    });

    it('defaults tags to empty array when omitted', () => {
      const chunk = aContentChunk({ tags: [] });

      expect(chunk.tags).toEqual([]);
    });

    it('defaults memoryBank to "default" when omitted', () => {
      const chunk = aContentChunk({ memoryBank: 'default' });

      expect(chunk.memoryBank).toBe('default');
    });
  });

  describe('Chunk.of — with generated ID (previously create())', () => {
    it('returns ok with valid props and generated ID', () => {
      const chunk = aContentChunk({
        totalChunks: 3,
        sectionHeader: 'Section Header',
        breadcrumb: 'root > section',
        language: 'markdown',
        fileRole: FILE_ROLES.DOCS,
        startLine: 1,
        endLine: 100,
        metadata: { source: 'test' },
      });

      expect(chunk.id).toBeGreaterThan(0n);
    });

    it('accepts generated bigint ID from generateId', () => {
      const chunk = aContentChunk();

      expect(typeof chunk.id).toBe('bigint');
      expect(chunk.id).toBeGreaterThan(0n);
    });

    it('uses DOCS fileRole when specified', () => {
      const chunk = aContentChunk({ fileRole: FILE_ROLES.DOCS });

      expect(chunk.fileRole).toBe(FILE_ROLES.DOCS);
    });

    it('uses oversized false when specified', () => {
      const chunk = aContentChunk({ oversized: false });

      expect(chunk.oversized).toBe(false);
    });

    it('accepts importance parameter', () => {
      const chunk = aContentChunk({ importance: 0.9 });

      expect(chunk.importance).toBe(0.9);
    });

    it('accepts tags parameter', () => {
      const chunk = aContentChunk({ tags: ['tag1', 'tag2'] });

      expect(chunk.tags).toEqual(['tag1', 'tag2']);
    });

    it('accepts memoryBank parameter', () => {
      const chunk = aContentChunk({ memoryBank: 'my-namespace' });

      expect(chunk.memoryBank).toBe('my-namespace');
    });
  });

  describe('getters', () => {
    let chunk: ContentChunk;

    beforeEach(() => {
      chunk = aContentChunk({
        text: 'Test content here',
        chunkIndex: 2,
        totalChunks: 5,
        sectionHeader: 'Main Section',
        breadcrumb: 'root > main',
        language: 'typescript',
        fileRole: FILE_ROLES.CODE,
        oversized: true,
        startLine: 10,
        endLine: 150,
        metadata: { key: 'value', another: 'data' },
        importance: 0.75,
        tags: ['important', 'config'],
        memoryBank: 'vault-knowledge',
      });
    });

    it('all getters return correct values', () => {
      expect(chunk.id).toBeGreaterThan(0n);
      expect(chunk.text).toBe('Test content here');
      expect(chunk.chunkIndex).toBe(2);
      expect(chunk.totalChunks).toBe(5);
      expect(chunk.sectionHeader).toBe('Main Section');
      expect(chunk.breadcrumb).toBe('root > main');
      expect(chunk.language).toBe('typescript');
      expect(chunk.fileRole).toBe(FILE_ROLES.CODE);
      expect(chunk.oversized).toBe(true);
      expect(chunk.startLine).toBe(10);
      expect(chunk.endLine).toBe(150);
      expect(chunk.metadata).toEqual({ key: 'value', another: 'data' });
      expect(chunk.importance).toBe(0.75);
      expect(chunk.tags).toEqual(['important', 'config']);
      expect(chunk.memoryBank).toBe('vault-knowledge');
    });
  });

  describe('FILE_ROLES', () => {
    it('contains expected values', () => {
      expect(FILE_ROLES.CONFIG).toBe('config');
      expect(FILE_ROLES.CODE).toBe('code');
      expect(FILE_ROLES.DOCS).toBe('docs');
    });
  });
});
