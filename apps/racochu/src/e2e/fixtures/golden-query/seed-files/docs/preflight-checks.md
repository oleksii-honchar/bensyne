# Pre-Flight Checks Before Switching Embedding Model

Before switching the embedding model, run these pre-flight checks:

## 1. Gateway Connectivity

Verify the LiteLLM gateway is reachable:

```bash
curl -H "Authorization: Bearer $MNEMOSYNE_EMBEDDING_API_KEY" \
  https://lite-llm.lan/v1/models
```

Expected: HTTP 200 with model list.

## 2. Embeddings Endpoint

Test the embeddings endpoint with a sample query:

```bash
curl -H "Authorization: Bearer $MNEMOSYNE_EMBEDDING_API_KEY" \
  https://lite-llm.lan/v1/embeddings \
  -d '{"model": "puma-embed-qwen3-4b", "input": ["hello"]}'
```

Expected: HTTP 200 with embedding vector of dimension 2560.

## 3. Gateway Key Validation

Ensure the gateway key (MNEMOSYNE_EMBEDDING_API_KEY) is valid and has
access to the embedding model. A 401/403 response indicates an invalid key.

## 4. Mnemosyne Doctor

Run mnemosyne doctor to verify the current server state before switching.
