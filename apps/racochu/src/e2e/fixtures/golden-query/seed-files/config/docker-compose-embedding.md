# Docker Compose Embedding Configuration

The docker-compose pattern for Mnemosyne injects the embedding API key
via Infisical. The MNEMOSYNE_EMBEDDING_API_KEY is managed as an
external secret in the Infisical secret store.

The docker-compose service sets:
- MNEMOSYNE_EMBEDDING_MODEL: puma-embed-qwen3-4b
- MNEMOSYNE_EMBEDDING_DIM: 2560
- MNEMOSYNE_EMBEDDING_API_URL: https://lite-llm.lan/v1
