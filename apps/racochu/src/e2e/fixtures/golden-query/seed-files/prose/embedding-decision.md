# Embedding Model Switch Decision

## Decision: Switch to Qwen3-Embedding-4B

The team decided to switch the embedding model from BAAI/bge-small-en-v1.5
to Qwen3-Embedding-4B, accessed via the LiteLLM gateway at
https://lite-llm.lan/v1 using the model name puma-embed-qwen3-4b.

### Rationale

- Qwen3-Embedding-4B provides 2560-dimensional vectors with 8192-token context,
  a significant upgrade over the 384-dim 512-token limit of the previous model.
- The LiteLLM gateway provides a unified OpenAI-compatible endpoint,
  simplifying the embedding pipeline.

### Implementation

- Set MNEMOSYNE_EMBEDDING_MODEL=puma-embed-qwen3-4b
- Set MNEMOSYNE_EMBEDDING_DIM=2560
- One-time reindex required (--no-backup flag)
