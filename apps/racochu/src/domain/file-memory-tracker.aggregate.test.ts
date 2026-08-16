import { FileMemoryTracker } from './file-memory-tracker.aggregate';

describe('FileMemoryTracker', () => {
  const validProps = {
    id: 1n,
    filePath: '/test/file.txt',
    memoryIds: ['mem-001'],
    sourceId: 'source-001',
    memoryBank: 'vault-knowledge',
  };

  describe('of', () => {
    it('with valid props returns ok with tracker', () => {
      const result = FileMemoryTracker.of(validProps);

      expect(result.isOk()).toBe(true);
      const tracker = result.getValue();
      expect(tracker.id).toBe(validProps.id);
      expect(typeof tracker.id).toBe('bigint');
      expect(tracker.filePath).toBe(validProps.filePath);
      expect(tracker.memoryIds).toEqual(validProps.memoryIds);
      expect(tracker.sourceId).toBe(validProps.sourceId);
      expect(tracker.memoryBank).toBe(validProps.memoryBank);
    });

    it('with string id returns ko (id must be a bigint)', () => {
      const result = FileMemoryTracker.of({
        ...validProps,
        id: 'tracker-001' as unknown as bigint,
      });

      expect(result.isKo()).toBe(true);
    });

    it('with empty filePath returns ko', () => {
      const result = FileMemoryTracker.of({
        ...validProps,
        filePath: '',
      });

      expect(result.isKo()).toBe(true);
    });

    it('with empty memoryIds returns ok (allowed for findOrCreate)', () => {
      const result = FileMemoryTracker.of({
        ...validProps,
        memoryIds: [],
      });

      expect(result.isOk()).toBe(true);
      expect(result.getValue().memoryIds).toEqual([]);
    });

    it('with empty sourceId returns ko', () => {
      const result = FileMemoryTracker.of({
        ...validProps,
        sourceId: '',
      });

      expect(result.isKo()).toBe(true);
    });

    it('with empty memoryBank returns ko', () => {
      const result = FileMemoryTracker.of({
        ...validProps,
        memoryBank: '',
      });

      expect(result.isKo()).toBe(true);
    });

    it('with missing required fields returns ko', () => {
      const result = FileMemoryTracker.of({
        id: 1n,
        filePath: '/test/file.txt',
        // missing memoryIds, sourceId, memoryBank
      } as never);

      expect(result.isKo()).toBe(true);
    });

    it('with invalid filePath returns ko', () => {
      const result = FileMemoryTracker.of({
        ...validProps,
        filePath: '',
      });

      expect(result.isKo()).toBe(true);
    });
  });

  describe('of', () => {
    it('with valid props returns ok', () => {
      const result = FileMemoryTracker.of({
        id: 1n,
        filePath: '/test/file.txt',
        memoryIds: ['mem-001', 'mem-002'],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      });

      expect(result.isOk()).toBe(true);
      const tracker = result.getValue();
      expect(tracker.id).toBe(1n);
      expect(tracker.filePath).toBe('/test/file.txt');
      expect(tracker.memoryIds).toEqual(['mem-001', 'mem-002']);
      expect(tracker.sourceId).toBe('source-001');
      expect(tracker.memoryBank).toBe('vault-knowledge');
    });

    it('with invalid filePath returns ko', () => {
      const result = FileMemoryTracker.of({
        id: 1n,
        filePath: '',
        memoryIds: ['mem-001'],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      });

      expect(result.isKo()).toBe(true);
    });

    it('with empty memoryIds returns ok (allowed for findOrCreate)', () => {
      const result = FileMemoryTracker.of({
        id: 1n,
        filePath: '/test/file.txt',
        memoryIds: [],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      });

      expect(result.isOk()).toBe(true);
      expect(result.getValue().memoryIds).toEqual([]);
    });

    it('with missing required fields returns ko', () => {
      const result = FileMemoryTracker.of({
        id: 1n,
        filePath: '/test/file.txt',
        // missing memoryIds, sourceId, memoryBank
      } as never);

      expect(result.isKo()).toBe(true);
    });
  });

  describe('remember', () => {
    it('appends new memoryId to list', () => {
      const tracker = FileMemoryTracker.of(validProps).getValue();

      const result = tracker.remember('mem-002');

      expect(result.isOk()).toBe(true);
      const updated = result.getValue();
      expect(updated.memoryIds).toEqual(['mem-001', 'mem-002']);
    });

    it('returns new instance without mutating original', () => {
      const tracker = FileMemoryTracker.of(validProps).getValue();

      tracker.remember('mem-002');

      expect(tracker.memoryIds).toEqual(['mem-001']);
    });

    it('does not add duplicate memoryId', () => {
      const tracker = FileMemoryTracker.of(validProps).getValue();

      const result = tracker.remember('mem-001');

      expect(result.isOk()).toBe(true);
      const updated = result.getValue();
      expect(updated.memoryIds).toEqual(['mem-001']);
    });

    it('with empty memoryId returns ko', () => {
      const tracker = FileMemoryTracker.of(validProps).getValue();

      const result = tracker.remember('');

      expect(result.isKo()).toBe(true);
    });
  });

  describe('forget', () => {
    it('removes existing memoryId from list', () => {
      const tracker = FileMemoryTracker.of({
        id: 1n,
        filePath: '/test/file.txt',
        memoryIds: ['mem-001', 'mem-002', 'mem-003'],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      }).getValue();

      const result = tracker.forget('mem-002');

      expect(result.isOk()).toBe(true);
      const updated = result.getValue();
      expect(updated.memoryIds).toEqual(['mem-001', 'mem-003']);
    });

    it('returns new instance without mutating original', () => {
      const tracker = FileMemoryTracker.of({
        id: 1n,
        filePath: '/test/file.txt',
        memoryIds: ['mem-001', 'mem-002'],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      }).getValue();

      tracker.forget('mem-001');

      expect(tracker.memoryIds).toEqual(['mem-001', 'mem-002']);
    });

    it('returns original unchanged when memoryId not found', () => {
      const tracker = FileMemoryTracker.of({
        id: 1n,
        filePath: '/test/file.txt',
        memoryIds: ['mem-001'],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      }).getValue();

      const result = tracker.forget('mem-999');

      expect(result.isOk()).toBe(true);
      const updated = result.getValue();
      expect(updated.memoryIds).toEqual(['mem-001']);
    });
  });

  describe('getters', () => {
    let tracker: FileMemoryTracker;

    beforeEach(() => {
      const result = FileMemoryTracker.of({
        id: 1n,
        filePath: '/test/file.txt',
        memoryIds: ['mem-001', 'mem-002'],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      });
      tracker = result.getValue();
    });

    it('all getters return correct values', () => {
      expect(tracker.id).toBe(1n);
      expect(tracker.filePath).toBe('/test/file.txt');
      expect(tracker.memoryIds).toEqual(['mem-001', 'mem-002']);
      expect(tracker.sourceId).toBe('source-001');
      expect(tracker.memoryBank).toBe('vault-knowledge');
    });
  });

  describe('toJson', () => {
    it('returns plain object with Prisma record shape', () => {
      const tracker = FileMemoryTracker.of({
        id: 1n,
        filePath: '/test/file.txt',
        memoryIds: ['mem-001', 'mem-002'],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      }).getValue();

      const json = tracker.toJson();

      expect(json).toEqual({
        id: 1n,
        filePath: '/test/file.txt',
        memoryIds: ['mem-001', 'mem-002'],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      });
    });

    it('returns new object each call (not cached reference)', () => {
      const tracker = FileMemoryTracker.of(validProps).getValue();

      const json1 = tracker.toJson();
      const json2 = tracker.toJson();

      expect(json1).toEqual(json2);
      expect(json1).not.toBe(json2);
    });
  });
});
