# Embedding Service Fallback Runbook

## When LiteLLM or llama-swap is Down

If the LiteLLM gateway or llama-swap is unavailable, follow this procedure:

1. **Check LiteLLM health**: curl https://lite-llm.lan/v1/models
2. **Check llama-swap**: Ensure the llama-swap config-1 is active
3. **If down, enable fallback**:
   - The system automatically falls back to keyword search
   - Vector search is disabled until the service recovers
4. **Monitor**: Watch logs for "keyword search fallback" warnings
5. **Recover**: When LiteLLM is back, restart the chunker to resume
   vector search with the embedding model

## Common Issues

- **401 Unauthorized**: Check MNEMOSYNE_EMBEDDING_API_KEY in .env
- **Connection refused**: llama-swap may be down — restart the container
- **Timeout**: The LiteLLM gateway may be overloaded — reduce concurrency
