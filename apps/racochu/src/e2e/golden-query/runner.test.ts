import { isContentHit, normalizeText, runGoldenQueries, scoreQuery } from './runner';

describe('golden-query runner helpers', () => {
  describe('normalizeText', () => {
    it('lowercases and collapses whitespace', () => {
      expect(normalizeText('  Hello   World\n  ')).toBe('hello world');
    });
  });

  describe('isContentHit', () => {
    it('matches expected content as normalized substring', () => {
      expect(isContentHit(['embedding dimension'], 'The EMBEDDING  dimension is resolved via env var')).toBe(
        true,
      );
    });

    it('returns false when expected content absent', () => {
      expect(isContentHit(['vector search'], 'chunking strategy config')).toBe(false);
    });

    it('ignores empty expected snippets', () => {
      expect(isContentHit([''], 'anything')).toBe(false);
    });
  });

  describe('scoreQuery', () => {
    it('scores perfect retrieval (all relevant at top)', () => {
      const s = scoreQuery(['alpha beta'], ['alpha beta gamma', 'unrelated one']);
      expect(s.recallAt5).toBe(1);
      expect(s.precisionAt5).toBeCloseTo(1 / 5);
      expect(s.mrr).toBe(1);
    });

    it('scores first hit at rank 3 with partial recall', () => {
      const s = scoreQuery(['needle'], ['miss1', 'miss2', 'needle text', 'miss3', 'miss4']);
      expect(s.recallAt5).toBe(1);
      expect(s.mrr).toBeCloseTo(1 / 3);
    });

    it('scores zero when no hits', () => {
      const s = scoreQuery(['needle'], ['miss1', 'miss2', 'miss3']);
      expect(s.recallAt5).toBe(0);
      expect(s.precisionAt5).toBe(0);
      expect(s.mrr).toBe(0);
    });

    it('only counts hits within top-5 toward recall', () => {
      const s = scoreQuery(['needle'], ['miss1', 'miss2', 'miss3', 'miss4', 'miss5', 'needle text']);
      expect(s.recallAt5).toBe(0);
      expect(s.mrr).toBeCloseTo(1 / 6); // MRR still sees rank 6
    });
  });

  describe('runGoldenQueries', () => {
    const corpus = [
      {
        id: 'golden-prose-01',
        contentType: 'prose' as const,
        query: 'embedding decision?',
        expectedMemoryIds: ['k1'],
      },
      {
        id: 'golden-code-01',
        contentType: 'code' as const,
        query: 'dim resolution?',
        expectedMemoryIds: ['k2'],
      },
    ];

    it('aggregates metrics across queries', async () => {
      const report = await runGoldenQueries({
        mode: 'baseline',
        corpus,
        recall: async query =>
          query.includes('embedding') ? ['the embedding decision was made'] : ['unrelated'],
        resolveExpectedContent: key => (key === 'k1' ? ['embedding decision'] : ['dim resolution']),
      });
      expect(report.queryCount).toBe(2);
      expect(report.perQuery[0].mrr).toBe(1);
      expect(report.perQuery[1].mrr).toBe(0);
      expect(report.aggregate.mrr).toBeCloseTo(0.5);
    });

    it('flags blocking MRR drop when baseline supplied', async () => {
      const report = await runGoldenQueries({
        mode: 'post-switch',
        corpus,
        recall: async () => ['unrelated'],
        resolveExpectedContent: key => ['whatever'],
        baseline: { recallAt5: 0.8, precisionAt5: 0.6, mrr: 0.7 },
      });
      expect(report.mrrDropBlocking).toBe(true);
    });

    it('does not flag when MRR improves', async () => {
      const report = await runGoldenQueries({
        mode: 'post-switch',
        corpus,
        recall: async query => ['the embedding decision was made', 'dim resolution happens via env'],
        resolveExpectedContent: key => (key === 'k1' ? ['embedding decision'] : ['dim resolution']),
        baseline: { recallAt5: 0.2, precisionAt5: 0.1, mrr: 0.2 },
      });
      expect(report.mrrDropBlocking).toBe(false);
    });

    it('handles empty retrieval gracefully (scores 0, no throw)', async () => {
      const report = await runGoldenQueries({
        mode: 'baseline',
        corpus,
        recall: async () => [],
        resolveExpectedContent: key => ['x'],
      });
      expect(report.perQuery.every(q => q.mrr === 0)).toBe(true);
    });
  });
});
