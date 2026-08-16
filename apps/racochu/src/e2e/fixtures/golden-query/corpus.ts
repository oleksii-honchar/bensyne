/**
 * Golden-query corpus — ground-truth retrieval queries for RAG validation.
 *
 * Each query targets content that would be ingested from racochu watch sources
 * (agent session notes, code files, config files, documentation). The
 * `expectedMemoryIds` are stable keys that the runner maps to actual stored
 * memory IDs (via a corpus manifest / fixture mapping) before scoring.
 *
 * Content types: prose | code | configuration | documentation
 */

export const GOLDEN_QUERY_CONTENT_TYPES = ['prose', 'code', 'configuration', 'documentation'] as const;

export type GoldenQueryContentType = (typeof GOLDEN_QUERY_CONTENT_TYPES)[number];

export interface GoldenQueryEntry {
  /** Stable unique id (e.g. golden-prose-01). */
  id: string;
  /** Content type label. */
  contentType: GoldenQueryContentType;
  /** Natural-language retrieval query. */
  query: string;
  /** Ground-truth relevant memory keys (mapped to stored memory IDs at run time). */
  expectedMemoryIds: string[];
}

export const GOLDEN_QUERY_CORPUS: GoldenQueryEntry[] = [
  // ---------- prose ----------
  {
    id: 'golden-prose-01',
    contentType: 'prose',
    query: 'What was decided in the session about switching the embedding model?',
    expectedMemoryIds: ['mem-prose-embedding-decision'],
  },
  {
    id: 'golden-prose-02',
    contentType: 'prose',
    query: 'How does the file watcher debounce handle rapid consecutive file changes?',
    expectedMemoryIds: ['mem-prose-debounce'],
  },
  {
    id: 'golden-prose-03',
    contentType: 'prose',
    query: 'What are the success criteria for the RAG content chunker tool?',
    expectedMemoryIds: ['mem-prose-success-criteria'],
  },
  {
    id: 'golden-prose-04',
    contentType: 'prose',
    query: 'Explain the graceful degradation behavior when the embedding service is unavailable',
    expectedMemoryIds: ['mem-prose-fallback'],
  },
  {
    id: 'golden-prose-05',
    contentType: 'prose',
    query: 'What is the purpose of the mnemosyne doctor command and what does it report?',
    expectedMemoryIds: ['mem-prose-doctor'],
  },

  // ---------- code ----------
  {
    id: 'golden-code-01',
    contentType: 'code',
    query: 'How is the embedding dimension resolved in the embeddings module?',
    expectedMemoryIds: ['mem-code-embedding-dim'],
  },
  {
    id: 'golden-code-02',
    contentType: 'code',
    query: 'Where is the LiteLLM gateway API key read for embedding requests?',
    expectedMemoryIds: ['mem-code-api-key'],
  },
  {
    id: 'golden-code-03',
    contentType: 'code',
    query: 'Show the chunking strategy router that selects between mastra, session, and obsidian strategies',
    expectedMemoryIds: ['mem-code-strategy-router'],
  },
  {
    id: 'golden-code-04',
    contentType: 'code',
    query: 'How does the metric module compute mean reciprocal rank?',
    expectedMemoryIds: ['mem-code-mrr'],
  },
  {
    id: 'golden-code-05',
    contentType: 'code',
    query: 'What code handles the dimension mismatch guard for vec0 tables?',
    expectedMemoryIds: ['mem-code-vec-guard'],
  },

  // ---------- configuration ----------
  {
    id: 'golden-config-01',
    contentType: 'configuration',
    query: 'What are the maxCharacters limits for prose and code in the racochu config?',
    expectedMemoryIds: ['mem-config-maxchars'],
  },
  {
    id: 'golden-config-02',
    contentType: 'configuration',
    query: 'Which environment variable names configure the Mnemosyne embedding model and dimension?',
    expectedMemoryIds: ['mem-config-env-vars'],
  },
  {
    id: 'golden-config-03',
    contentType: 'configuration',
    query: 'What is the docker-compose pattern for injecting the embedding API key via Infisical?',
    expectedMemoryIds: ['mem-config-infisical'],
  },
  {
    id: 'golden-config-04',
    contentType: 'configuration',
    query: 'Which watch source strategy is configured for the agent-sessions directory?',
    expectedMemoryIds: ['mem-config-watch-source'],
  },
  {
    id: 'golden-config-05',
    contentType: 'configuration',
    query: 'What are the enrichment settings — is enrichment enabled and which model is used?',
    expectedMemoryIds: ['mem-config-enrichment'],
  },

  // ---------- documentation ----------
  {
    id: 'golden-doc-01',
    contentType: 'documentation',
    query: 'How do you run the golden-query regression suite after a retrieval change?',
    expectedMemoryIds: ['mem-doc-golden-query'],
  },
  {
    id: 'golden-doc-02',
    contentType: 'documentation',
    query: 'What is the runbook procedure when LiteLLM or llama-swap is down?',
    expectedMemoryIds: ['mem-doc-runbook'],
  },
  {
    id: 'golden-doc-03',
    contentType: 'documentation',
    query: 'How is the one-time reindex with no backup performed?',
    expectedMemoryIds: ['mem-doc-reindex'],
  },
  {
    id: 'golden-doc-04',
    contentType: 'documentation',
    query: 'What are the pre-flight checks before switching the embedding model?',
    expectedMemoryIds: ['mem-doc-preflight'],
  },
  {
    id: 'golden-doc-05',
    contentType: 'documentation',
    query: 'Which ADRs document the embedding switch and the chunk size bump decisions?',
    expectedMemoryIds: ['mem-doc-adrs'],
  },
];
