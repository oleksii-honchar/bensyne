/**
 * Embedding dimension resolution for the Mnemosyne MCP client.
 */

import { ConfigurationService } from '../config/configuration.service';

export class EmbeddingDimensionResolver {
  constructor(private readonly config: ConfigurationService) {}

  /**
   * Resolves the embedding dimension from environment or config.
   * Reads MNEMOSYNE_EMBEDDING_DIM (expected: 2560 for Qwen3).
   */
  _get_embedding_dim(): number {
    const fromEnv = process.env.MNEMOSYNE_EMBEDDING_DIM;
    if (fromEnv) {
      const dim = parseInt(fromEnv, 10);
      if (!isNaN(dim)) return dim;
    }

    // Fallback to config value
    const configDim = this.config.get<number>('embedding.dimension');
    if (typeof configDim === 'number') return configDim;

    // Default: 2560 for Qwen3-Embedding-4B
    return 2560;
  }
}
