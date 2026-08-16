/**
 * Pure metric functions for golden-query retrieval validation.
 *
 * Metrics computed from actual retrieval results (top-5 candidate memory IDs
 * per query vs ground-truth relevant IDs). These are pure functions — no I/O,
 * no logging — so they are trivially unit-testable.
 */

export interface GoldenQueryResult {
  /** Query identifier from the corpus. */
  queryId: string;
  /** Content type label: prose | code | configuration | documentation. */
  contentType: string;
  /** Ground-truth relevant memory IDs for this query. */
  relevantIds: string[];
  /** Top-5 candidate memory IDs returned by Mnemosyne recall, in rank order. */
  retrievedIds: string[];
}

export interface GoldenQueryMetrics {
  recallAt5: number;
  precisionAt5: number;
  mrr: number;
}

/**
 * Recall@5 — fraction of relevant items found in the top-5 candidates.
 * relevant ∩ top5 / |relevant|. 0 when there are no relevant items (guarded).
 */
export function recallAt5(relevantIds: string[], retrievedIds: string[]): number {
  if (relevantIds.length === 0) {
    return 0;
  }
  const top5 = retrievedIds.slice(0, 5);
  const hitCount = relevantIds.filter(id => top5.includes(id)).length;
  return hitCount / relevantIds.length;
}

/**
 * Precision@5 — fraction of the top-5 candidates that are relevant.
 * relevant ∩ top5 / 5. Uses full 5 denominator per standard Precision@k.
 */
export function precisionAt5(relevantIds: string[], retrievedIds: string[]): number {
  const top5 = retrievedIds.slice(0, 5);
  if (top5.length === 0) {
    return 0;
  }
  const hitCount = relevantIds.filter(id => top5.includes(id)).length;
  return hitCount / 5;
}

/**
 * MRR — reciprocal rank of the first relevant item in the candidate list.
 * 1/rank where rank is 1-based position of first hit; 0 if no hit.
 */
export function mrr(relevantIds: string[], retrievedIds: string[]): number {
  for (let i = 0; i < retrievedIds.length; i++) {
    if (relevantIds.includes(retrievedIds[i])) {
      return 1 / (i + 1);
    }
  }
  return 0;
}

/**
 * Compute all three metrics for a single query result.
 */
export function computeMetrics(result: GoldenQueryResult): GoldenQueryMetrics {
  return {
    recallAt5: recallAt5(result.relevantIds, result.retrievedIds),
    precisionAt5: precisionAt5(result.relevantIds, result.retrievedIds),
    mrr: mrr(result.relevantIds, result.retrievedIds),
  };
}

/**
 * Aggregate metrics across all query results (mean of per-query values).
 * Returns zeros when there are no results.
 */
export function aggregateMetrics(results: GoldenQueryResult[]): GoldenQueryMetrics {
  if (results.length === 0) {
    return { recallAt5: 0, precisionAt5: 0, mrr: 0 };
  }
  const perQuery = results.map(computeMetrics);
  const sum = (key: keyof GoldenQueryMetrics): number => perQuery.reduce((acc, m) => acc + m[key], 0);
  return {
    recallAt5: sum('recallAt5') / results.length,
    precisionAt5: sum('precisionAt5') / results.length,
    mrr: sum('mrr') / results.length,
  };
}

/**
 * Compute per-metric delta between two aggregate reports (new - baseline).
 * A NEGATIVE MRR delta exceeding 10% (absolute) is the blocking signal per
 * ADR-0055: flag MRR drop > 0.10.
 */
export function metricDeltas(
  baseline: GoldenQueryMetrics,
  current: GoldenQueryMetrics,
): { recallAt5: number; precisionAt5: number; mrr: number; mrrDropBlocking: boolean } {
  const recallAt5 = current.recallAt5 - baseline.recallAt5;
  const precisionAt5 = current.precisionAt5 - baseline.precisionAt5;
  const mrr = current.mrr - baseline.mrr;
  const mrrDropBlocking = mrr < -0.1;
  return { recallAt5, precisionAt5, mrr, mrrDropBlocking };
}
