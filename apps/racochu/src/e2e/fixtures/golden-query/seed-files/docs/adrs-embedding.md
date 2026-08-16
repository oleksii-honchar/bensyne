# ADRs Related to Embedding Enhancement

## ADR-0052: Switch to Qwen3-Embedding-4B via LiteLLM Gateway

Switched the embedding model from BAAI/bge-small-en-v1.5 (384-dim) to
Qwen3-Embedding-4B (2560-dim) via the LiteLLM gateway. The model is
accessed as puma-embed-qwen3-4b at https://lite-llm.lan/v1.

## ADR-0054: RACochu maxCharacters Bump

Increased maxCharacters limits to take advantage of the larger embedding
context window: prose → 4000, code → 5000, configuration → 1500,
documentation → 4000.

## ADR-0055: Golden-Query Validation

Added golden-query regression suite to validate retrieval quality after
embedding model changes. Metrics: Recall@5, Precision@5, MRR.

## ADR-0056: Health-Check and Fallback

Added health-check for the LiteLLM gateway and fallback to keyword search
when the embedding service is unavailable.
