/**
 * Expected-content manifest for golden-query scoring.
 *
 * Maps each corpus memory key to the content snippets that SHOULD be
 * retrievable from Mnemosyne for the corresponding query. The runner scores a
 * retrieved item as a hit when its content contains one of these snippets.
 *
 * These snippets are derived from the actual feature context (env vars,
 * configs, ADRs, code) — keep them aligned with real ingested content.
 */

export const GOLDEN_QUERY_EXPECTED_CONTENT: Record<string, string[]> = {
  // prose
  'mem-prose-embedding-decision': [
    'puma-embed-qwen3-4b',
    'Qwen3-Embedding-4B',
    'embedding model',
    'LiteLLM gateway',
  ],
  'mem-prose-debounce': ['debounce', 'chokidar', 'file watcher', '5000'],
  'mem-prose-success-criteria': ['success criteria', 'RAG content chunker', 'chunking'],
  'mem-prose-fallback': ['keyword search', 'fallback', 'degrade', 'no crash', 'graceful'],
  'mem-prose-doctor': ['mnemosyne doctor', 'embeddings', 'health'],

  // code
  'mem-code-embedding-dim': ['MNEMOSYNE_EMBEDDING_DIM', '2560', '_get_embedding_dim'],
  'mem-code-api-key': ['MNEMOSYNE_EMBEDDING_API_KEY', 'Authorization', 'Bearer'],
  'mem-code-strategy-router': ['StrategyRouter', 'content-aware', 'agent-sessions', 'obsidian'],
  'mem-code-mrr': ['mrr', 'reciprocal rank', 'recallAt5', 'precisionAt5'],
  'mem-code-vec-guard': ['dimension mismatch', 'vec0', 'beam', 'keyword'],

  // configuration
  'mem-config-maxchars': ['maxCharacters', 'prose', '4000', 'code', '5000'],
  'mem-config-env-vars': ['MNEMOSYNE_EMBEDDING_MODEL', 'MNEMOSYNE_EMBEDDING_DIM', 'MNEMOSYNE_EMBEDDING_API_URL'],
  'mem-config-infisical': ['Infisical', 'MNEMOSYNE_EMBEDDING_API_KEY', 'docker-compose'],
  'mem-config-watch-source': ['agent-sessions', 'watchSources', 'strategy'],
  'mem-config-enrichment': ['enrichment', 'enabled', 'llmUrl', 'lite-llm'],

  // documentation
  'mem-doc-golden-query': ['golden-query', 'regression', 'Recall@5', 'MRR', 'run'],
  'mem-doc-runbook': ['runbook', 'LiteLLM', 'llama-swap', 'down', 'fallback'],
  'mem-doc-reindex': ['reindex', '--no-backup', '2560'],
  'mem-doc-preflight': ['pre-flight', 'curl', 'embeddings', 'gateway key'],
  'mem-doc-adrs': ['ADR-0052', 'ADR-0054', 'ADR-0055', 'embedding'],
};
