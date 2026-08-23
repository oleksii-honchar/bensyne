import { createOpenAI } from '@ai-sdk/openai';
import type { MastraLanguageModel, MastraLegacyLanguageModel } from '@mastra/core/agent';

export interface EnrichmentConfigForLlm {
  enabled: boolean;
  llmUrl: string;
  llmModel: string;
  apiKey: string;
  /**
   * Upper bound on the number of output tokens the enrichment LLM may generate.
   * Applied per generation (doGenerate/doStream), NOT globally.
   */
  maxOutputTokens: number;
}

type GenerateFn = (args: Record<string, unknown>) => Promise<unknown>;

/**
 * Wrap a language model so every generation carries a `maxOutputTokens` bound.
 *
 * The @ai-sdk/openai provider maps `maxOutputTokens` to `max_tokens` in the
 * underlying Chat Completions call (verified in OpenAIChatLanguageModel.getArgs).
 * The provider factory in this SDK version (`chat(modelId)`) does not accept
 * per-model settings, so the bound is injected at the generation-call layer.
 * The wrapper keeps the original prototype (getters like `modelId`/`provider`
 * keep working) and only overrides `doGenerate`/`doStream`.
 */
function withMaxOutputTokens<T extends object>(model: T, maxOutputTokens: number): T {
  const wrapped = Object.create(Object.getPrototypeOf(model)) as T & {
    doGenerate?: GenerateFn;
    doStream?: GenerateFn;
  };
  Object.assign(wrapped, model);

  const source = model as T & { doGenerate?: GenerateFn; doStream?: GenerateFn };
  const bound =
    (fn: GenerateFn): GenerateFn =>
    args =>
      fn.call(model, { ...args, maxOutputTokens });

  if (typeof source.doGenerate === 'function') {
    wrapped.doGenerate = bound(source.doGenerate);
  }
  if (typeof source.doStream === 'function') {
    wrapped.doStream = bound(source.doStream);
  }

  return wrapped as T;
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
    const model: object =
      typeof provider.chat === 'function'
        ? (provider.chat(config.llmModel) as object)
        : typeof prov.chatModel === 'function'
          ? (prov.chatModel(config.llmModel) as object)
          : (provider(config.llmModel) as object);
    // Bound the enrichment output: without a cap, llama.cpp defaults allow
    // degenerate run-away responses (observed: a single 403KB+ repeated-token value).
    return withMaxOutputTokens(model, config.maxOutputTokens) as MastraLanguageModel;
  }
}
