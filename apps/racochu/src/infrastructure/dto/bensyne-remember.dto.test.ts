import { createHash } from 'crypto';
import { readFileSync } from 'fs';
import { join } from 'path';
import { aBodyChunk, aContentChunk } from '../../domain/content-chunk.entity.test-utils';
import unifiedChunkContractV1Fixture from './fixtures/unified-chunk-contract-v1.json';
import { BensyneRememberDto, MnemosyneRememberPayload } from './bensyne-remember.dto';

type FixtureChunkProps = Omit<Parameters<typeof aContentChunk>[0], 'id'> & { id: string };

interface FixtureShape {
  description: string;
  content: string;
  memory_bank: string;
  importance: number;
  source: string;
  fixtureChunk: FixtureChunkProps;
  metadata: Record<string, unknown>;
}

const fixture = unifiedChunkContractV1Fixture as unknown as FixtureShape;

describe('BensyneRememberDto', () => {
  describe('fromChunk — unified chunk contract v1', () => {
    it('maps the canonical fixture chunk to metadata deep-equal to the fixture (all 15 v1 keys exact)', () => {
      const chunk = aContentChunk({ ...fixture.fixtureChunk, id: BigInt(fixture.fixtureChunk.id) });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata).toEqual(fixture.metadata);
      // Transport envelope keys asserted against the same fixture file (parity gate, spec §7.4)
      expect(dto.content).toBe(fixture.content);
      expect(dto.memory_bank).toBe(fixture.memory_bank);
      expect(dto.importance).toBe(fixture.importance);
      expect(dto.source).toBe(fixture.source);
      // Hash discipline (contract rule 4b): hashes live in metadata only — no top-level hash arg
      expect(dto).not.toHaveProperty('hash');
      expect(dto.metadata.file_hash).toBe('ed8feb0ec28dad93b0c1e85377908f07367164d374d3d329e1bde6668591cc17');
      // Dual-hash wire contract (D13): chunk_hash = sha256 of the exact chunk text
      expect(dto.metadata.chunk_hash).toBe('aee858233038e696cb0c90d0d65a312c308454104a6bd4bbb53554f7816b322c');
    });

    it('maps legacy flat keys to v1 snake_case keys without top-level dialect leakage', () => {
      const chunk = aContentChunk({
        breadcrumb: '/vault/notes/meeting.md',
        chunkIndex: 3,
        totalChunks: 7,
        sectionHeader: '## Decisions',
        startLine: 10,
        endLine: 25,
        fileRole: 'docs' as const,
        language: undefined,
        tags: ['meeting'],
        metadata: { filePath: '/vault/notes/meeting.md', sourceId: 'file_system' },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata).toEqual({
        contract_version: 1,
        file_path: '/vault/notes/meeting.md',
        chunk_index: 3,
        total_chunks: 7,
        section_header: '## Decisions',
        start_line: 10,
        end_line: 25,
        source_type: 'file_system',
        file_role: 'docs',
        summary: null,
        tags: ['meeting'],
      });
      // No legacy flat keys may leak to top level
      expect(dto.metadata).not.toHaveProperty('breadcrumb');
      expect(dto.metadata).not.toHaveProperty('chunkIndex');
      expect(dto.metadata).not.toHaveProperty('totalChunks');
      expect(dto.metadata).not.toHaveProperty('sectionHeader');
      expect(dto.metadata).not.toHaveProperty('fileRole');
      expect(dto.metadata).not.toHaveProperty('filePath');
      expect(dto.metadata).not.toHaveProperty('sourceId');
      // No leftover legacy keys ⇒ no `extra` key at all
      expect(dto.metadata).not.toHaveProperty('extra');
    });

    it('omits file_path when the chunk carries no source path (plain-memory path)', () => {
      const chunk = aContentChunk({
        breadcrumb: '',
        metadata: {},
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata).not.toHaveProperty('file_path');
    });

    it('sets metadata.file_hash from the internal fileHash when the file hash is available', () => {
      const chunk = aContentChunk({
        metadata: { filePath: '/a/b.md', sourceId: 'file_system', fileHash: 'sha256-file-hash-value' },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.file_hash).toBe('sha256-file-hash-value');
      // No top-level hash argument on the remember payload (contract rule 4b)
      expect(dto).not.toHaveProperty('hash');
    });

    it('sets metadata.chunk_hash from the internal chunkHash (camelCase→snake_case translation)', () => {
      const chunk = aContentChunk({
        metadata: { filePath: '/a/b.md', sourceId: 'file_system', chunkHash: 'sha256-chunk-hash-value' },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.chunk_hash).toBe('sha256-chunk-hash-value');
      // Internal camelCase key must not leak into metadata or extra
      expect(dto.metadata).not.toHaveProperty('chunkHash');
      expect(dto.metadata.extra ?? {}).not.toHaveProperty('chunkHash');
    });

    it('emits exactly metadata.chunk_hash + metadata.file_hash for a chunk carrying both hashes (byte-check)', () => {
      const chunk = aBodyChunk({
        text: 'exact chunk text',
        metadata: {
          filePath: '/vault/a.md',
          sourceId: 'file_system',
          fileHash: 'b'.repeat(64),
          chunkHash: 'a'.repeat(64),
        },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      const expected = {
        content: 'exact chunk text',
        memory_bank: 'default',
        importance: 0.5,
        source: 'default',
        metadata: {
          contract_version: 1,
          file_path: '/vault/a.md',
          chunk_index: 0,
          total_chunks: 1,
          section_header: 'Test Section',
          source_type: 'file_system',
          file_role: 'docs',
          file_hash: 'b'.repeat(64),
          chunk_hash: 'a'.repeat(64),
          summary: null,
          tags: [],
        },
      };

      expect(JSON.stringify(dto)).toBe(JSON.stringify(expected));
    });

    it('omits metadata.chunk_hash (not null, not empty) when the chunk has no internal chunkHash', () => {
      const chunk = aContentChunk({
        metadata: { filePath: '/a/b.md', sourceId: 'file_system', fileHash: 'sha256-file-hash-value' },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata).not.toHaveProperty('chunk_hash');
      expect(dto.metadata.file_hash).toBe('sha256-file-hash-value');
    });

    it('omits metadata.file_hash when the file hash is unavailable', () => {
      const chunk = aContentChunk({
        breadcrumb: '',
        metadata: {},
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata).not.toHaveProperty('file_hash');
    });

    it('passes edges through intact when present', () => {
      const chunk = aContentChunk({
        metadata: {},
        edges: [
          { target_path: '/root/session.md', relation_type: 'parent_child' as const, strength: 1 },
          {
            target_path: '/root/materials/contract.md',
            relation_type: 'sibling' as const,
            strength: 1,
            description: 'companion artifact',
          },
        ],
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.edges).toEqual([
        { target_path: '/root/session.md', relation_type: 'parent_child', strength: 1 },
        {
          target_path: '/root/materials/contract.md',
          relation_type: 'sibling',
          strength: 1,
          description: 'companion artifact',
        },
      ]);
    });

    it('omits the edges key when the chunk has no edges', () => {
      const chunk = aContentChunk({ metadata: {} });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata).not.toHaveProperty('edges');
    });

    it('captures session.* and note.* keys verbatim in extra', () => {
      const chunk = aContentChunk({
        breadcrumb: '/vault/notes/deep.md',
        metadata: {
          filePath: '/vault/notes/deep.md',
          sourceId: 'agent_session',
          'session.id': '260811-0000',
          'session.status': 'in-progress',
          'note.aliases': '["Deep Dive"]',
          'note.properties.kind': 'note',
        },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.extra).toEqual({
        'session.id': '260811-0000',
        'session.status': 'in-progress',
        'note.aliases': '["Deep Dive"]',
        'note.properties.kind': 'note',
      });
      // Consumed keys must not leak into extra or top level
      expect(dto.metadata).not.toHaveProperty('filePath');
      expect(dto.metadata).not.toHaveProperty('sourceId');
      expect(dto.metadata.source_type).toBe('agent_session');
    });

    it('derives parent_unit from session.* metadata when present', () => {
      const chunk = aContentChunk({
        breadcrumb: '/sessions/260811-0000/findings.md',
        metadata: {
          filePath: '/sessions/260811-0000/findings.md',
          sourceId: 'agent_session',
          'session.id': '260811-0000',
          'session.status': 'in-progress',
        },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.parent_unit).toEqual({ ref: 'session-260811-0000', summary: 'in-progress' });
    });

    it('omits parent_unit for sources without a parent-unit concept (no session.id)', () => {
      const chunk = aContentChunk({
        breadcrumb: '/vault/notes/plain.md',
        metadata: { filePath: '/vault/notes/plain.md', sourceId: 'file_system' },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata).not.toHaveProperty('parent_unit');
    });

    it('maps envelope fields (content, memory_bank, importance, source) from the chunk', () => {
      const chunk = aContentChunk({
        text: 'envelope body',
        memoryBank: 'obsidian-notes',
        importance: 0.85,
        metadata: {},
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.content).toBe('envelope body');
      expect(dto.memory_bank).toBe('obsidian-notes');
      expect(dto.importance).toBe(0.85);
      expect(dto.source).toBe('obsidian-notes');
    });

    it('omits optional v1 keys when the chunk does not carry them', () => {
      const chunk = aContentChunk({
        startLine: undefined,
        endLine: undefined,
        language: undefined,
        metadata: {},
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata).not.toHaveProperty('start_line');
      expect(dto.metadata).not.toHaveProperty('end_line');
      expect(dto.metadata).not.toHaveProperty('language');
      expect(dto.metadata).not.toHaveProperty('source_type');
    });

    it.each([
      ['file_system', 'file_system'],
      ['agent_session', 'agent_session'],
      ['git', 'git'],
      ['database', 'database'],
      ['external', 'external'],
      ['remote', 'remote'],
      ['unknown_source_id', undefined],
    ])('maps sourceId %s to source_type %s (identity map, unknown omitted)', (sourceId, expected) => {
      const chunk = aContentChunk({
        metadata: { sourceId },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      if (expected === undefined) {
        expect(dto.metadata).not.toHaveProperty('source_type');
      } else {
        expect(dto.metadata.source_type).toBe(expected);
      }
    });
  });

  describe('contract parity (spec §7.4)', () => {
    it('pins the fixture file bytes to the recorded parity sha256', () => {
      const raw = readFileSync(join(__dirname, 'fixtures', 'unified-chunk-contract-v1.json'));

      expect(createHash('sha256').update(raw).digest('hex')).toBe(
        '02c99bb5aac5b367d8a6271a43baff48b145d1c6def64dd8258e4c6958a52887',
      );
    });

    it('asserts metadata.chunk_hash == sha256 of the exact content string (normalization-drift guard)', () => {
      const expected = createHash('sha256').update(fixture.content).digest('hex');

      expect(fixture.metadata.chunk_hash).toBe(expected);
    });
  });

  describe('payload shape (transport envelope)', () => {
    it('keeps the rememberMemory argument keys stable (content, memory_bank, importance, source, metadata — no top-level hash)', () => {
      const chunk = aContentChunk({
        metadata: { fileHash: 'h-1', chunkHash: 'c-1' },
      });

      const dto: MnemosyneRememberPayload = BensyneRememberDto.fromChunk(chunk);

      expect(Object.keys(dto).sort()).toEqual(['content', 'importance', 'memory_bank', 'metadata', 'source']);
    });
  });
});
