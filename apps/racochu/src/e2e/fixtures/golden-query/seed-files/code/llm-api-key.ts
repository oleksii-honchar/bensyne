/**
 * LiteLLM gateway API key resolution for embedding requests.
 */

import { ConfigurationService } from '../config/configuration.service';

export class LiteLLMApiKeyResolver {
  constructor(private readonly config: ConfigurationService) {}

  /**
   * Resolves the API key for the LiteLLM gateway.
   * Reads MNEMOSYNE_EMBEDDING_API_KEY from environment.
   * Sets Authorization: Bearer <key> header on requests.
   */
  resolveApiKey(): string | null {
    const fromEnv = process.env.MNEMOSYNE_EMBEDDING_API_KEY;
    if (fromEnv && fromEnv.trim().length > 0) {
      return fromEnv.trim();
    }

    const fromConfig = this.config.get<string>('enrichment.apiKey');
    if (typeof fromConfig === 'string' && fromConfig.length > 0) {
      return fromConfig;
    }

    return null;
  }

  /**
   * Builds the Authorization header value for the LiteLLM gateway.
   */
  buildAuthHeader(): string | null {
    const key = this.resolveApiKey();
    if (!key) return null;
    return 'Bearer ' + key;
  }
}
