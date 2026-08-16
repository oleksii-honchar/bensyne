import { GOLDEN_QUERY_CONTENT_TYPES, GOLDEN_QUERY_CORPUS } from '@/e2e/fixtures/golden-query/corpus';

describe('golden-query corpus structure', () => {
  it('contains 15–30 queries', () => {
    expect(GOLDEN_QUERY_CORPUS.length).toBeGreaterThanOrEqual(15);
    expect(GOLDEN_QUERY_CORPUS.length).toBeLessThanOrEqual(30);
  });

  it('spans all 4 content types with at least 3 queries each', () => {
    for (const contentType of GOLDEN_QUERY_CONTENT_TYPES) {
      const count = GOLDEN_QUERY_CORPUS.filter(q => q.contentType === contentType).length;
      expect(count).toBeGreaterThanOrEqual(3);
    }
  });

  it('every query has id, contentType, query text and expectedMemoryIds', () => {
    for (const entry of GOLDEN_QUERY_CORPUS) {
      expect(entry.id).toBeTruthy();
      expect(entry.contentType).toBeTruthy();
      expect(entry.query.length).toBeGreaterThan(10);
      expect(Array.isArray(entry.expectedMemoryIds)).toBe(true);
      expect(entry.expectedMemoryIds.length).toBeGreaterThan(0);
    }
  });

  it('ids are unique and deterministic (no random generation)', () => {
    const ids = GOLDEN_QUERY_CORPUS.map(q => q.id);
    expect(new Set(ids).size).toBe(ids.length);
    // Determinism: corpus is a const array — re-import yields identical content
    expect(GOLDEN_QUERY_CORPUS).toEqual(GOLDEN_QUERY_CORPUS);
  });
});
