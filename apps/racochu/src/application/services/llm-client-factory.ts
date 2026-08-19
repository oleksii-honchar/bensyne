import { createOpenAI } from '@ai-sdk/openai';
import type { MastraLanguageModel, MastraLegacyLanguageModel } from '@mastra/core/agent';

export interface EnrichmentConfigForLlm {
  enabled: boolean;
  llmUrl: string;
  llmModel: string;
  apiKey: string;
}

export class LlmClientFactory {
  static createCustomLlm(
    config: EnrichmentConfigForLlm,
  ): MastraLegacyLanguageModel | MastraLanguageModel | null {
    if (!config.enabled || !config.llmUrl || !config.apiKey) {
      return null;
    }
    const provider = createOpenAI({
      apiKey: config.apiKey,
      baseURL: config.llmUrl,
    });
    // @ai-sdk/openai v4+ uses .chat(); @ai-sdk/openai-v6 (3.x, used by Mastra) uses .chatModel().
    // The provider is also callable: provider(modelId) returns the model.
    // We handle all cases by preferring .chat(), then .chatModel(), then the callable form.
    // Avoid .bind() — the @ai-sdk/openai-v6 provider has Symbol keys that break bind().
    const prov = provider as typeof provider & { chatModel?: (id: string) => unknown };
    const model =
      typeof provider.chat === 'function'
        ? provider.chat(config.llmModel)
        : typeof prov.chatModel === 'function'
          ? prov.chatModel(config.llmModel)
          : provider(config.llmModel);
    return model as MastraLanguageModel;
  }
}
