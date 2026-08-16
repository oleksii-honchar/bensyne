import { GoldenQueryEntry } from '@/e2e/fixtures/golden-query/corpus';
import { GoldenQueryMetrics } from './metrics';

/**
 * Relevance matching for golden-query scoring.
 *
 * Mnemosyne recall returns content strings (not memory IDs), so a retrieved
 * item counts as a hit when it contains the expected content for the query.
 * Matching is normalized (lowercase, whitespace-collapsed) substring matching.
 */
export function normalizeText(text: string): string {
  return text.toLowerCase().replace(/\s+/g, ' ').trim();
}

export function isContentHit(expectedContents: string[], retrievedContent: string): boolean {
  const normalized = normalizeText(retrievedContent);
  return expectedContents.some(
    expected => normalizeText(expected).length > 0 && normalized.includes(normalizeText(expected)),
  );
}

/** Rank-ordered hit flags for retrieved contents (true = relevant). */
export function hitRanks(expectedContents: string[], retrievedContents: string[]): boolean[] {
  return retrievedContents.map(content => isContentHit(expectedContents, content));
}

export type RecallFn = (query: string) => Promise<string[]>;

export interface GoldenQueryRunOptions {
  /** Mode label: 'baseline' | 'post-switch' — recorded in the report. */
  mode: string;
  /** Corpus entries to score. */
  corpus: GoldenQueryEntry[];
  /** Executes a query against Mnemosyne recall; returns retrieved content list in rank order. */
  recall: RecallFn;
  /** Maps a corpus memory key to the expected content snippets for that key. */
  resolveExpectedContent: (memoryKey: string) => string[];
  /** Optional baseline aggregate metrics; enables the >10% MRR-drop blocking flag. */
  baseline?: GoldenQueryMetrics;
}

export interface PerQueryScored {
  id: string;
  contentType: string;
  query: string;
  /** Number of relevant expected snippets. */
  relevantCount: number;
  /** Number of hits in the top-5 retrieved items. */
  hitsInTop5: number;
  /** Total retrieved items (recall limit). */
  retrievedCount: number;
  recallAt5: number;
  precisionAt5: number;
  mrr: number;
}

export interface GoldenQueryRunReport {
  mode: string;
  generatedAt: string;
  queryCount: number;
  perQuery: PerQueryScored[];
  aggregate: GoldenQueryMetrics;
  /** Present only when a baseline was supplied. */
  mrrDropBlocking?: boolean;
}

/**
 * Score a single query's retrieval.
 * - recallAt5 = relevant hits in top-5 / total relevant snippets (0-guarded)
 * - precisionAt5 = relevant hits in top-5 / 5 (standard Precision@5 denominator)
 * - mrr = 1 / rank of first hit (0 if no hit)
 */
export function scoreQuery(
  expectedContents: string[],
  retrievedContents: string[],
): Pick<
  PerQueryScored,
  'relevantCount' | 'hitsInTop5' | 'retrievedCount' | 'recallAt5' | 'precisionAt5' | 'mrr'
> {
  const relevantCount = expectedContents.length;
  const top5 = retrievedContents.slice(0, 5);
  const hitsInTop5 = hitRanks(expectedContents, top5).filter(Boolean).length;
  const firstHitIndex = hitRanks(expectedContents, retrievedContents).findIndex(Boolean);

  return {
    relevantCount,
    hitsInTop5,
    retrievedCount: retrievedContents.length,
    recallAt5: relevantCount > 0 ? hitsInTop5 / relevantCount : 0,
    precisionAt5: hitsInTop5 / 5,
    mrr: firstHitIndex >= 0 ? 1 / (firstHitIndex + 1) : 0,
  };
}

/**
 * Runs all corpus queries through the provided recall function and scores
 * Recall@5 / Precision@5 / MRR. Never throws on empty retrieval — a query
 * with zero results simply scores 0.
 */
export async function runGoldenQueries(options: GoldenQueryRunOptions): Promise<GoldenQueryRunReport> {
  const perQuery: PerQueryScored[] = [];

  for (const entry of options.corpus) {
    const expectedContents = entry.expectedMemoryIds.flatMap(key => options.resolveExpectedContent(key));
    const retrieved = await options.recall(entry.query);
    const scored = scoreQuery(expectedContents, retrieved);

    perQuery.push({
      id: entry.id,
      contentType: entry.contentType,
      query: entry.query,
      ...scored,
    });
  }

  const aggregate: GoldenQueryMetrics =
    perQuery.length === 0
      ? { recallAt5: 0, precisionAt5: 0, mrr: 0 }
      : {
          recallAt5: perQuery.reduce((sum, q) => sum + q.recallAt5, 0) / perQuery.length,
          precisionAt5: perQuery.reduce((sum, q) => sum + q.precisionAt5, 0) / perQuery.length,
          mrr: perQuery.reduce((sum, q) => sum + q.mrr, 0) / perQuery.length,
        };

  const report: GoldenQueryRunReport = {
    mode: options.mode,
    generatedAt: new Date().toISOString(),
    queryCount: perQuery.length,
    perQuery,
    aggregate,
  };

  if (options.baseline) {
    report.mrrDropBlocking = aggregate.mrr < options.baseline.mrr - 0.1;
  }

  return report;
}
