/**
 * Golden-query metrics computation.
 *
 * Computes Recall@5, Precision@5, and Mean Reciprocal Rank (MRR)
 * for retrieval evaluation.
 */

export interface GoldenQueryMetrics {
  recallAt5: number;
  precisionAt5: number;
  mrr: number;
}

/**
 * Computes the mean reciprocal rank for a list of per-query MRR values.
 * MRR = 1 / rank_of_first_hit, or 0 if no hit.
 */
export function computeMRR(perQueryMrr: number[]): number {
  if (perQueryMrr.length === 0) return 0;
  return perQueryMrr.reduce((sum, val) => sum + val, 0) / perQueryMrr.length;
}

/**
 * Computes Recall@5: fraction of relevant items retrieved in top-5.
 */
export function computeRecallAt5(hitsInTop5: number, totalRelevant: number): number {
  if (totalRelevant === 0) return 0;
  return hitsInTop5 / totalRelevant;
}

/**
 * Computes Precision@5: fraction of top-5 that are relevant.
 */
export function computePrecisionAt5(hitsInTop5: number): number {
  return hitsInTop5 / 5;
}

/**
 * Aggregates per-query scores into aggregate metrics.
 */
export function aggregateMetrics(
  perQuery: Array<{ recallAt5: number; precisionAt5: number; mrr: number }>,
): GoldenQueryMetrics {
  if (perQuery.length === 0) return { recallAt5: 0, precisionAt5: 0, mrr: 0 };

  return {
    recallAt5: perQuery.reduce((s, q) => s + q.recallAt5, 0) / perQuery.length,
    precisionAt5: perQuery.reduce((s, q) => s + q.precisionAt5, 0) / perQuery.length,
    mrr: perQuery.reduce((s, q) => s + q.mrr, 0) / perQuery.length,
  };
}
