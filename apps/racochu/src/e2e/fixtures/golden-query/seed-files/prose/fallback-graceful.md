# Graceful Degradation — Embedding Service Unavailable

When the embedding service (LiteLLM gateway) is unavailable, the system
must degrade gracefully without crashing. The following fallback strategy
is implemented:

1. The file watcher continues to process files normally.
2. Embedding ingestion to Mnemosyne is retried with exponential backoff.
3. If the service remains unavailable after all retries, keyword search
   is used as a fallback for retrieval instead of vector search.
4. The system does not crash — it logs warnings and continues operation.
5. When the service becomes available again, pending embeddings are
   reprocessed and the system returns to normal vector search mode.

This graceful degradation ensures no crash occurs when the embedding
pipeline is temporarily broken.
