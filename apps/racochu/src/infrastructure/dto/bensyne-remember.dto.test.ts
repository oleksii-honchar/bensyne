import { aContentChunk } from '../../domain/content-chunk.entity.test-utils';
import { BensyneRememberDto } from './bensyne-remember.dto';

describe('BensyneRememberDto', () => {
  describe('fromChunk', () => {
    it('maps all required chunk properties to remember payload', () => {
      const chunk = aContentChunk();
      const props = chunk.toJson();

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.content).toBe(props.text);
      expect(dto.memory_bank).toBe(props.memoryBank);
      expect(dto.importance).toBe(props.importance);
      expect(dto.source).toBe(props.memoryBank);
      expect(dto.metadata).toEqual(
        expect.objectContaining({
          id: props.id,
          chunkIndex: props.chunkIndex,
          totalChunks: props.totalChunks,
          sectionHeader: props.sectionHeader,
          breadcrumb: props.breadcrumb,
          fileRole: props.fileRole,
          startLine: props.startLine,
          endLine: props.endLine,
          importance: props.importance,
          tags: props.tags,
          memoryBank: props.memoryBank,
        }),
      );
    });

    it('includes language in metadata when present', () => {
      const chunk = aContentChunk({
        language: 'typescript',
        fileRole: 'code' as const,
      });
      const props = chunk.toJson();

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.language).toBe(props.language);
    });

    it('omits language from metadata when not present', () => {
      const chunk = aContentChunk({
        language: undefined,
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.language).toBeUndefined();
    });

    it('omits startLine and endLine from metadata when not present', () => {
      const chunk = aContentChunk({
        startLine: undefined,
        endLine: undefined,
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.startLine).toBeUndefined();
      expect(dto.metadata.endLine).toBeUndefined();
    });

    it('merges chunk metadata into result metadata', () => {
      const chunk = aContentChunk({
        metadata: {
          customKey: 'customValue',
          anotherKey: 'anotherValue',
        },
      });
      const props = chunk.toJson();

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.customKey).toBe(props.metadata?.customKey);
      expect(dto.metadata.anotherKey).toBe(props.metadata?.anotherKey);
      // Standard fields still present
      expect(dto.metadata.id).toBe(props.id);
      expect(dto.metadata.memoryBank).toBe(props.memoryBank);
    });

    it('uses default values for chunk with defaults', () => {
      const chunk = aContentChunk({
        tags: [],
      });
      const props = chunk.toJson();

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.memory_bank).toBe(props.memoryBank);
      expect(dto.importance).toBe(props.importance);
      expect(dto.source).toBe(props.memoryBank);
      expect(dto.metadata.memoryBank).toBe(props.memoryBank);
      expect(dto.metadata.importance).toBe(props.importance);
      expect(dto.metadata.tags).toEqual(props.tags);
      expect(dto.metadata.fileRole).toBe(props.fileRole);
    });

    it('includes fileHash in metadata when present in chunk metadata', () => {
      const chunk = aContentChunk({
        metadata: { fileHash: 'abc123def456' },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.fileHash).toBe('abc123def456');
    });

    it('includes hardwareId in metadata when present in chunk metadata', () => {
      const chunk = aContentChunk({
        metadata: { hardwareId: 'hw-98765' },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.hardwareId).toBe('hw-98765');
    });

    it('includes both fileHash and hardwareId in metadata when both present', () => {
      const chunk = aContentChunk({
        metadata: { fileHash: 'sha256-abc', hardwareId: 'hw-xyz' },
      });

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.metadata.fileHash).toBe('sha256-abc');
      expect(dto.metadata.hardwareId).toBe('hw-xyz');
      // Standard fields still present
      expect(dto.metadata.id).toBeDefined();
      expect(dto.metadata.memoryBank).toBeDefined();
    });

    it('sets source equal to memory bank (not literal "chunk")', () => {
      const chunk = aContentChunk({
        memoryBank: 'obsidian-notes',
      });
      const props = chunk.toJson();

      const dto = BensyneRememberDto.fromChunk(chunk);

      expect(dto.source).toBe(props.memoryBank);
      expect(dto.source).not.toBe('chunk');
    });
  });
});
