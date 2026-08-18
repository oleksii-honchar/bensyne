import { z } from 'zod';
import { SOURCE_TYPES } from './source-types';

export const watchSourceConfigSchema = z
  .object({
    id: z.string(),
    path: z.string(),
    memoryBank: z.string().optional(),
    description: z.string().optional(),
    exclude: z.array(z.string()).default(['.git/**', '**/.git/**', 'node_modules/**', '**/node_modules/**']),
    debounceMs: z.number().positive().default(3000),
    // D29: the field IS the source type (default vault, the content-aware
    // successor). `unknown` is the wire-side fallback only.
    sourceType: z
      .enum(Object.values(SOURCE_TYPES) as [string, ...string[]])
      .optional()
      .default(SOURCE_TYPES.VAULT),
  })
  .transform(data => ({
    ...data,
    memoryBank: data.memoryBank ?? data.id,
  }));

export const importanceFactorConfigSchema = z.object({
  name: z.string(),
  weight: z.number().default(1.0),
});

export const enhancementConfigSchema = z
  .object({
    maxCharacters: z
      .object({
        prose: z.number().positive(),
        code: z.number().positive(),
        configuration: z.number().positive(),
        documentation: z.number().positive(),
      })
      .optional(),
    importance: z
      .object({
        enabled: z.boolean(),
        defaultScore: z.number().min(0).max(1),
        factors: z.array(importanceFactorConfigSchema).optional(),
      })
      .transform(data => ({
        enabled: data.enabled ?? true,
        defaultScore: data.defaultScore ?? 0.5,
        factors: data.factors ?? [
          { name: 'fileRole', weight: 0.4 },
          { name: 'length', weight: 0.2 },
          { name: 'keywords', weight: 0.3 },
          { name: 'header', weight: 0.1 },
        ],
      }))
      .optional(),
    tags: z
      .object({
        enabled: z.boolean(),
        maxTags: z.number().positive(),
      })
      .optional(),
    source: z
      .object({
        includePath: z.boolean(),
        includeSection: z.boolean(),
        includeMetadata: z.boolean(),
      })
      .optional(),
  })
  .transform(data => ({
    maxCharacters: {
      prose: data.maxCharacters?.prose ?? 200,
      code: data.maxCharacters?.code ?? 400,
      configuration: data.maxCharacters?.configuration ?? 300,
      documentation: data.maxCharacters?.documentation ?? 300,
    },
    importance: data.importance ?? {
      enabled: true,
      defaultScore: 0.5,
      factors: [
        { name: 'fileRole', weight: 0.4 },
        { name: 'length', weight: 0.2 },
        { name: 'keywords', weight: 0.3 },
        { name: 'header', weight: 0.1 },
      ],
    },
    tags: {
      enabled: data.tags?.enabled ?? true,
      maxTags: data.tags?.maxTags ?? 10,
    },
    source: {
      includePath: data.source?.includePath ?? true,
      includeSection: data.source?.includeSection ?? true,
      includeMetadata: data.source?.includeMetadata ?? false,
    },
  }));

export const chunkingConfigSchema = z
  .object({
    maxSizes: z
      .object({
        agentSessions: z.number().optional(),
        obsidianNotes: z.number().optional(),
        codeFiles: z.number().optional(),
        configuration: z.union([z.number(), z.string()]).optional(),
        plainText: z.number().optional(),
      })
      .optional(),
    overlap: z.number().optional(),
    hardCap: z.number().optional(),
  })
  .transform(data => ({
    maxSizes: {
      agentSessions: data.maxSizes?.agentSessions ?? 400,
      obsidianNotes: data.maxSizes?.obsidianNotes ?? 500,
      codeFiles: data.maxSizes?.codeFiles ?? 400,
      configuration: data.maxSizes?.configuration ?? 'per-key',
      plainText: data.maxSizes?.plainText ?? 450,
    },
    overlap: data.overlap ?? 50,
    hardCap: data.hardCap ?? 600,
  }));

export const enrichmentConfigSchema = z
  .object({
    enabled: z.boolean().optional(),
    llmUrl: z.url().optional(),
    llmModel: z.string().optional(),
    apiKey: z.string().optional(),
    maxConcurrency: z.number().positive().optional(),
    timeoutMs: z.number().positive().optional(),
    docMaxTokens: z.number().positive().optional(),
  })
  .transform(data => ({
    enabled: data.enabled ?? false,
    llmUrl: data.llmUrl,
    llmModel: data.llmModel,
    apiKey: data.apiKey,
    maxConcurrency: data.maxConcurrency ?? 1,
    timeoutMs: data.timeoutMs ?? 15000,
    docMaxTokens: data.docMaxTokens ?? 16000,
  }));

export const mcpConfigSchema = z
  .object({
    url: z.url().optional(),
    apiKey: z.string().optional(),
    timeoutMs: z.number().positive().optional(),
    maxRetries: z.number().positive().optional(),
    retryDelayMs: z.number().positive().optional(),
  })
  .transform(data => ({
    url: data.url ?? 'https://lite-llm.lan/mcp/mnemosyne',
    apiKey: data.apiKey,
    timeoutMs: data.timeoutMs ?? 30000,
    maxRetries: data.maxRetries ?? 3,
    retryDelayMs: data.retryDelayMs ?? 1000,
  }));

export const telemetryConfigSchema = z
  .object({
    enabled: z.boolean().optional(),
    endpoint: z.string().optional(),
    service: z.string().optional(),
    metrics: z
      .object({
        chunking: z.boolean().optional(),
        ingestion: z.boolean().optional(),
        errors: z.boolean().optional(),
      })
      .optional(),
  })
  .transform(data => ({
    enabled: data.enabled ?? true,
    endpoint: data.endpoint ?? 'clickstack-otel-collector:4317',
    service: data.service ?? 'racochu',
    metrics: {
      chunking: data.metrics?.chunking ?? true,
      ingestion: data.metrics?.ingestion ?? true,
      errors: data.metrics?.errors ?? true,
    },
  }));

// Root configuration schema — all nested sections are optional.
// When omitted, each section's internal defaults apply via transform.
export const configurationSchema = z
  .object({
    watchSources: z.array(watchSourceConfigSchema).optional().default([]),
    chunking: chunkingConfigSchema.optional(),
    enrichment: enrichmentConfigSchema.optional(),
    enhancement: enhancementConfigSchema.optional(),
    mcp: mcpConfigSchema.optional(),
    telemetry: telemetryConfigSchema.optional(),
  })
  .transform(data => ({
    watchSources: data.watchSources ?? [],
    chunking: {
      maxSizes: {
        agentSessions: data.chunking?.maxSizes?.agentSessions ?? 400,
        obsidianNotes: data.chunking?.maxSizes?.obsidianNotes ?? 500,
        codeFiles: data.chunking?.maxSizes?.codeFiles ?? 400,
        configuration: data.chunking?.maxSizes?.configuration ?? 'per-key',
        plainText: data.chunking?.maxSizes?.plainText ?? 450,
      },
      overlap: data.chunking?.overlap ?? 50,
      hardCap: data.chunking?.hardCap ?? 600,
    },
    enrichment: {
      enabled: data.enrichment?.enabled ?? false,
      llmUrl: data.enrichment?.llmUrl,
      llmModel: data.enrichment?.llmModel,
      apiKey: data.enrichment?.apiKey,
      maxConcurrency: data.enrichment?.maxConcurrency ?? 1,
      timeoutMs: data.enrichment?.timeoutMs ?? 15000,
      docMaxTokens: data.enrichment?.docMaxTokens ?? 16000,
    },
    enhancement: {
      maxCharacters: {
        prose: data.enhancement?.maxCharacters?.prose ?? 200,
        code: data.enhancement?.maxCharacters?.code ?? 400,
        configuration: data.enhancement?.maxCharacters?.configuration ?? 300,
        documentation: data.enhancement?.maxCharacters?.documentation ?? 300,
      },
      importance: {
        enabled: data.enhancement?.importance?.enabled ?? true,
        defaultScore: data.enhancement?.importance?.defaultScore ?? 0.5,
        factors: data.enhancement?.importance?.factors ?? [
          { name: 'fileRole', weight: 0.4 },
          { name: 'length', weight: 0.2 },
          { name: 'keywords', weight: 0.3 },
          { name: 'header', weight: 0.1 },
        ],
      },
      tags: {
        enabled: data.enhancement?.tags?.enabled ?? true,
        maxTags: data.enhancement?.tags?.maxTags ?? 10,
      },
      source: {
        includePath: data.enhancement?.source?.includePath ?? true,
        includeSection: data.enhancement?.source?.includeSection ?? true,
        includeMetadata: data.enhancement?.source?.includeMetadata ?? false,
      },
    },
    mcp: {
      url: data.mcp?.url ?? 'https://lite-llm.lan/mcp/mnemosyne',
      apiKey: data.mcp?.apiKey,
      timeoutMs: data.mcp?.timeoutMs ?? 30000,
      maxRetries: data.mcp?.maxRetries ?? 3,
      retryDelayMs: data.mcp?.retryDelayMs ?? 1000,
    },
    telemetry: {
      enabled: data.telemetry?.enabled ?? true,
      endpoint: data.telemetry?.endpoint ?? 'clickstack-otel-collector:4317',
      service: data.telemetry?.service ?? 'racochu',
      metrics: {
        chunking: data.telemetry?.metrics?.chunking ?? true,
        ingestion: data.telemetry?.metrics?.ingestion ?? true,
        errors: data.telemetry?.metrics?.errors ?? true,
      },
    },
  }));

export type Configuration = z.infer<typeof configurationSchema>;
export type WatchSourceConfig = z.infer<typeof watchSourceConfigSchema>;
export type ChunkingConfig = z.infer<typeof chunkingConfigSchema>;
export type EnhancementConfig = z.infer<typeof enhancementConfigSchema>;
export type EnrichmentConfig = z.infer<typeof enrichmentConfigSchema>;
export type McpConfig = z.infer<typeof mcpConfigSchema>;
export type TelemetryConfig = z.infer<typeof telemetryConfigSchema>;
