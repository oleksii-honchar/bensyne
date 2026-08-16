# Mnemosyne Doctor Command

The mnemosyne doctor command is a diagnostic tool that reports the health
of the Mnemosyne MCP server and its embedding configuration.

When run, mnemosyne doctor checks:

1. **Connectivity**: Can the server be reached at the configured URL?
2. **Embeddings**: Is the embedding model responding? Are the embeddings
   endpoint and dimension correctly configured?
3. **Memory banks**: Are the expected memory banks registered?
4. **Health**: Overall health status of the Mnemosyne instance.

The doctor command is useful for pre-flight checks before switching
embedding models or after a deployment.
