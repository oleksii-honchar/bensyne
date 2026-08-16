import { aggregateMetrics, computeMetrics, metricDeltas, mrr, precisionAt5, recallAt5 } from './metrics';

describe('golden-query metrics (pure functions)', () => {
  describe('recallAt5', () => {
    it('returns 1 when all relevant items are in top-5', () => {
      expect(recallAt5(['a', 'b'], ['a', 'b', 'c', 'd', 'e'])).toBe(1);
    });

    it('returns fraction when only some relevant items are in top-5', () => {
      expect(recallAt5(['a', 'b', 'c'], ['a', 'x', 'y', 'z', 'w'])).toBeCloseTo(1 / 3);
    });

    it('returns 0 when no relevant item is in top-5', () => {
      expect(recallAt5(['a'], ['x', 'y', 'z', 'w', 'v'])).toBe(0);
    });

    it('ignores relevant items beyond rank 5', () => {
      // 'b' is relevant but ranked 6th — must NOT count toward top-5 recall
      expect(recallAt5(['a', 'b'], ['a', 'x', 'y', 'z', 'w', 'b'])).toBeCloseTo(0.5);
    });

    it('guards against empty relevant set', () => {
      expect(recallAt5([], ['a', 'b'])).toBe(0);
    });
  });

  describe('precisionAt5', () => {
    it('returns fraction of top-5 that are relevant (denominator 5)', () => {
      expect(precisionAt5(['a', 'b'], ['a', 'b', 'x', 'y', 'z'])).toBeCloseTo(2 / 5);
    });

    it('returns 0 when no relevant item in top-5', () => {
      expect(precisionAt5(['a'], ['x', 'y', 'z', 'w', 'v'])).toBe(0);
    });

    it('uses denominator 5 even when fewer candidates returned', () => {
      expect(precisionAt5(['a'], ['a'])).toBeCloseTo(1 / 5);
    });

    it('guards against empty retrieved list', () => {
      expect(precisionAt5(['a'], [])).toBe(0);
    });
  });

  describe('mrr', () => {
    it('returns 1 when first candidate is relevant', () => {
      expect(mrr(['a'], ['a', 'b', 'c'])).toBe(1);
    });

    it('returns reciprocal of first-hit rank', () => {
      expect(mrr(['c'], ['a', 'b', 'c', 'd', 'e'])).toBeCloseTo(1 / 3);
    });

    it('returns 0 when no hit', () => {
      expect(mrr(['z'], ['a', 'b', 'c'])).toBe(0);
    });

    it('picks the FIRST relevant hit, not the best-ranked relevant', () => {
      // 'b' is relevant at rank 2 and 'a' at rank 4 — MRR uses rank 2
      expect(mrr(['a', 'b'], ['x', 'b', 'y', 'a'])).toBeCloseTo(0.5);
    });
  });

  describe('computeMetrics', () => {
    it('combines all three metrics for a result', () => {
      const metrics = computeMetrics({
        queryId: 'q1',
        contentType: 'prose',
        relevantIds: ['a', 'b'],
        retrievedIds: ['a', 'x', 'b', 'y', 'z'],
      });
      expect(metrics.recallAt5).toBe(1);
      expect(metrics.precisionAt5).toBeCloseTo(2 / 5);
      expect(metrics.mrr).toBe(1);
    });
  });

  describe('aggregateMetrics', () => {
    it('returns mean of per-query metrics', () => {
      const results = [
        { queryId: 'q1', contentType: 'prose', relevantIds: ['a'], retrievedIds: ['a', 'b', 'c', 'd', 'e'] },
        { queryId: 'q2', contentType: 'code', relevantIds: ['z'], retrievedIds: ['a', 'b', 'c', 'd', 'e'] },
      ];
      const agg = aggregateMetrics(results);
      expect(agg.recallAt5).toBeCloseTo(0.5);
      expect(agg.mrr).toBeCloseTo(0.5);
    });

    it('returns zeros for empty result set', () => {
      expect(aggregateMetrics([])).toEqual({ recallAt5: 0, precisionAt5: 0, mrr: 0 });
    });
  });

  describe('metricDeltas', () => {
    const baseline = { recallAt5: 0.5, precisionAt5: 0.4, mrr: 0.6 };

    it('computes positive deltas for improvement', () => {
      const deltas = metricDeltas(baseline, { recallAt5: 0.7, precisionAt5: 0.5, mrr: 0.8 });
      expect(deltas.recallAt5).toBeCloseTo(0.2);
      expect(deltas.precisionAt5).toBeCloseTo(0.1);
      expect(deltas.mrr).toBeCloseTo(0.2);
      expect(deltas.mrrDropBlocking).toBe(false);
    });

    it('flags MRR drop > 10% as blocking', () => {
      const deltas = metricDeltas(baseline, { recallAt5: 0.5, precisionAt5: 0.4, mrr: 0.45 });
      expect(deltas.mrr).toBeCloseTo(-0.15);
      expect(deltas.mrrDropBlocking).toBe(true);
    });

    it('does not flag small MRR drops', () => {
      const deltas = metricDeltas(baseline, { recallAt5: 0.5, precisionAt5: 0.4, mrr: 0.55 });
      expect(deltas.mrrDropBlocking).toBe(false);
    });
  });
});
