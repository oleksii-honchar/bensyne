import { LlmClientFactory } from '@/application/services/llm-client-factory';
import { ContentChunk, FILE_ROLES, FileRole } from '@/domain/content-chunk.entity';
import { ConfigurationService } from '@/infrastructure/config/configuration.service';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { generateId } from '@/utils/big-endian-id';
import { ErrorWithDetails } from '@/utils/error-with-details';
import { Result } from '@/utils/result';
import { MDocument } from '@mastra/rag';
import { Injectable, Optional } from '@nestjs/common';
import { z } from 'zod';

type MastraChunkStrategy = 'markdown' | 'recursive' | 'json' | 'sentence';
type MastraDocumentType = 'markdown' | 'json' | 'html' | 'text';

/**
 * Derive the LLM whole-file summary word cap from the enrichment `docMaxTokens` config.
 * clamp(floor(docMaxTokens/200), 20, 120); default 16000 → 80 words.
 */
export function deriveSummaryMaxWords(docMaxTokens: number): number {
  return Math.max(20, Math.min(120, Math.floor(docMaxTokens / 200)));
}

/**
 * Upper bound on the enrichment LLM output (in tokens). Without this cap the
 * llama.cpp defaults allow degenerate run-away responses (observed: a single
 * 403KB+ repeated-token `keywords` value).
 */
export const ENRICHMENT_MAX_OUTPUT_TOKENS_CAP = 1024;

/**
 * Derive the enrichment `maxOutputTokens` bound from the `docMaxTokens` config.
 * clamp(floor(docMaxTokens), 256, 1024); default 16000 → 1024.
 */
export function deriveEnrichmentMaxOutputTokens(docMaxTokens: number): number {
  return Math.max(256, Math.min(ENRICHMENT_MAX_OUTPUT_TOKENS_CAP, Math.floor(docMaxTokens)));
}

/**
 * Upper bound (in characters) for the enrichment `keywords` metadata value.
 * Guards against degenerate repeated-token output growing chunk metadata unbounded.
 */
export const MAX_ENRICHMENT_KEYWORDS_LENGTH = 500;

/**
 * Truncate a keywords string to the metadata cap. If it fits, return unchanged.
 */
export function truncateEnrichmentKeywords(
  keywords: string,
  maxLength: number = MAX_ENRICHMENT_KEYWORDS_LENGTH,
): string {
  return keywords.length <= maxLength ? keywords : keywords.slice(0, maxLength);
}

/**
 * Corrective instruction appended to the enrichment prompt when the first
 * `extractMetadata` attempt fails (e.g. schema-validation error). The retry is
 * bounded to exactly ONE additional attempt — never an unbounded loop.
 */
export const ENRICHMENT_CORRECTIVE_RETRY_INSTRUCTION =
  'The previous response failed validation. You MUST return all three fields: title, keywords, and summary. summary is required and must be a string.';

/**
 * Bounded retry budget for transient 429 `RateLimitError`s on a single per-chunk
 * enrichment call. `ENRICHMENT_429_MAX_RETRIES` additional attempts are allowed
 * after the initial one (so at most 3 LLM calls per chunk on the 429 path), each
 * preceded by the short backoff in `ENRICHMENT_429_BACKOFF_MS`. Combined with the
 * Task 8 corrective retry the total per-chunk LLM calls never exceed 3.
 */
export const ENRICHMENT_429_MAX_RETRIES = 2;
export const ENRICHMENT_429_BACKOFF_MS: readonly number[] = [250, 500];

/**
 * Identify a transient 429 rate-limit error (status/code, error name, or message).
 * Deliberately does NOT use a generic `isRetryable` flag so validation errors are
 * never backoff-retried here — those fall through to the Task 8 corrective retry.
 */
export function isRateLimitError(error: unknown): boolean {
  if (error === null || error === undefined || typeof error !== 'object') {
    return false;
  }
  const candidate = error as { statusCode?: unknown; status?: unknown; name?: unknown; message?: unknown };
  if (candidate.statusCode === 429 || candidate.status === 429) {
    return true;
  }
  if (typeof candidate.name === 'string' && /rate.?limit/i.test(candidate.name)) {
    return true;
  }
  if (
    typeof candidate.message === 'string' &&
    /(429|too many requests|rate.?limit)/i.test(candidate.message)
  ) {
    return true;
  }
  return false;
}

const sleep = (ms: number): Promise<void> => new Promise(resolve => setTimeout(resolve, ms));

@Injectable()
export class MastraChunkingService {
  /**
   * Zod schema for structured enrichment output.
   * Using schema-based extraction eliminates free-text parsing issues entirely.
   */
  private static readonly enrichmentSchema = z.object({
    title: z.string(),
    keywords: z.string(),
    summary: z.string(),
  });

  constructor(
    private readonly configService: ConfigurationService,
    private readonly logger: BasePinoLogger,
    /**
     * Backoff sleeper for 429 retries. Injected so tests can record delays without
     * real timers; defaults to the real `sleep`. Resolved as optional by Nest DI.
     */
    @Optional() private readonly sleepFn: (ms: number) => Promise<void> = sleep,
  ) {}
  /**
   * Get max characters limit for a given file role from enhancement config.
   */
  private getMaxCharacters(fileRole: FileRole): number {
    const maxChars = this.configService.getEnhancementConfig().maxCharacters;

    const map: Record<FileRole, number> = {
      [FILE_ROLES.DOCS]: maxChars.prose,
      [FILE_ROLES.CODE]: maxChars.code,
      [FILE_ROLES.CONFIG]: maxChars.configuration,
    };

    return map[fileRole] ?? maxChars.prose;
  }

  /**
   * Race a promise against the enrichment timeout so a hung generation aborts
   * within the configured `enrichment.timeoutMs` instead of blocking the file.
   * The timer is always cleared once the race settles.
   */
  private async withEnrichmentTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
    let timer: NodeJS.Timeout | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Enrichment timed out after ${timeoutMs}ms`)), timeoutMs);
    });
    try {
      return await Promise.race([promise, timeout]);
    } finally {
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    }
  }

  /**
   * Build the enrichment `instructions` string for `extractMetadata`.
   * When `corrective` is true, the corrective retry instruction is appended so
   * a retried attempt explicitly demands all three schema fields.
   */
  private buildEnrichmentInstructions(summaryMaxWords: number, corrective: boolean): string {
    const instructions = `You must respond ONLY with valid JSON.

Extract the following fields from the document:
- title: A concise title describing the content
- keywords: At most 10 concise, comma-separated keywords
- summary: A concise whole-file summary of the document, at most ${summaryMaxWords} words

ALL THREE fields (title, keywords, summary) are REQUIRED. None may be omitted and none may be null.

Respond in this format:
{
  "title": "string",
  "keywords": "keyword1, keyword2, keyword3",
  "summary": "string"
}

Do not include any other text, explanations, or markdown formatting.`;

    return corrective ? `${instructions}\n\n${ENRICHMENT_CORRECTIVE_RETRY_INSTRUCTION}` : instructions;
  }

  /**
   * Enrich ONE chunk by running schema extraction against a fresh single-chunk
   * MDocument. With exactly one node, Mastra's SchemaExtractor performs exactly
   * one LLM call; the caller awaits each chunk before starting the next, so
   * concurrency is always 1 (the whole-file `extractMetadata` ran `Promise.all`
   * over every chunk — the 429 root cause on a single-slot llama.cpp backend).
   *
   * The Task 6 prompt is preserved verbatim (via `buildEnrichmentInstructions`).
   * Transient 429 `RateLimitError`s get a bounded backoff retry (Task 10): up to
   * `ENRICHMENT_429_MAX_RETRIES` extra attempts (250ms, 500ms) before the chunk
   * is given up un-enriched. Non-429 failures (e.g. schema-validation errors)
   * are NOT backoff-retried — they fall through to the Task 8 corrective retry
   * (exactly ONE extra attempt). The per-chunk LLM call budget is therefore
   * bounded at 3 attempts total, and exhausted retries never abort the remaining
   * chunks. Task 7 bounds still apply per attempt (timeout via
   * `withEnrichmentTimeout`).
   */
  private async enrichChunk(
    chunk: { text: string; metadata?: Record<string, unknown> },
    llm: NonNullable<ReturnType<typeof LlmClientFactory.createCustomLlm>>,
    docType: MastraDocumentType,
    filePath: string,
    sourceId: string,
    summaryMaxWords: number,
    timeoutMs: number,
  ): Promise<void> {
    const attempt = (instructions: string) =>
      this.withEnrichmentTimeout(
        (async () => {
          const singleChunkDoc = this.createDocument(chunk.text, docType, filePath, sourceId);
          return singleChunkDoc.extractMetadata({
            schema: {
              schema: MastraChunkingService.enrichmentSchema,
              llm,
              instructions,
              metadataKey: 'enrichment',
            },
          });
        })(),
        timeoutMs,
      );

    try {
      // Initial attempt with bounded backoff on transient 429s.
      const enrichedDoc = await this.attemptWith429Backoff(() =>
        attempt(this.buildEnrichmentInstructions(summaryMaxWords, false)),
      );
      this.applyEnrichmentToChunk(chunk, enrichedDoc);
    } catch (error) {
      // All 429 backoff retries exhausted — transient, a corrective prompt would
      // not help. Leave the chunk un-enriched; the remaining chunks still enrich.
      if (isRateLimitError(error)) {
        this.logger.warn('[enrichment] Rate limit retries exhausted', {
          error: error instanceof Error ? error.message : String(error),
          retries: ENRICHMENT_429_MAX_RETRIES,
          filePath,
        });
        return;
      }
      // Non-429 failure (e.g. schema-validation error) — retry ONCE with a
      // corrective instruction (Task 8). If that also fails, the chunk is left
      // un-enriched and the remaining chunks still get enriched.
      try {
        const enrichedDoc = await attempt(this.buildEnrichmentInstructions(summaryMaxWords, true));
        this.applyEnrichmentToChunk(chunk, enrichedDoc);
      } catch (error2) {
        const err = error2 instanceof Error ? error2 : new Error(String(error2));
        this.logger.warn('[enrichment] ExtractMetadata failed', {
          error: err.message,
          stack: err.stack ?? 'no stack',
          filePath,
        });
      }
    }
  }

  /**
   * Run an attempt, retrying ONLY transient 429 rate-limit errors with a short
   * backoff. Each retry sleeps `ENRICHMENT_429_BACKOFF_MS[i]` before the next
   * call; after `ENRICHMENT_429_MAX_RETRIES` retries the last error propagates.
   * Any non-429 error propagates immediately — never retried here. Bounded by
   * construction: at most `1 + ENRICHMENT_429_MAX_RETRIES` attempts.
   */
  private async attemptWith429Backoff(attempt: () => Promise<MDocument>): Promise<MDocument> {
    let attemptNumber = 0;
    for (;;) {
      try {
        return await attempt();
      } catch (error) {
        if (attemptNumber < ENRICHMENT_429_MAX_RETRIES && isRateLimitError(error)) {
          await this.sleepFn(ENRICHMENT_429_BACKOFF_MS[attemptNumber]);
          attemptNumber += 1;
          continue;
        }
        throw error;
      }
    }
  }

  /**
   * Stamp the schema-extracted `enrichment` object from the enriched single-chunk
   * document onto the original chunk's metadata, preserving any pre-existing
   * metadata (filePath/sourceId). Keeps the exact output shape used downstream:
   * `chunk.metadata.enrichment` → `mastraDocTitle`/`mastraDocKeywords`/`mastraDocSummary`.
   */
  private applyEnrichmentToChunk(
    chunk: { text: string; metadata?: Record<string, unknown> },
    enrichedDoc: MDocument,
  ): void {
    const enrichedChunk = enrichedDoc.getDocs()[0];
    const enrichment = enrichedChunk?.metadata?.enrichment;
    if (enrichment !== undefined && enrichment !== null && typeof enrichment === 'object') {
      chunk.metadata = {
        ...(chunk.metadata ?? {}),
        enrichment: enrichment as Record<string, unknown>,
      };
    }
  }

  /**
   * Chunk a file using Mastra MDocument with type-aware processing.
   */
  async chunkFile(content: string, filePath: string, sourceId: string): Promise<Result<ContentChunk[]>> {
    try {
      if (!content.trim()) {
        return Result.ok([]);
      }

      const chunker = this.determineStrategy(filePath);
      const docType = this.determineDocumentType(filePath);
      const fileRole = this.determineFileRole(filePath);

      // Create MDocument using type-aware factory
      const document = this.createDocument(content, docType, filePath, sourceId);

      // Apply chunking with size config from enhancement.maxCharacters
      await this.applyChunking(document, chunker, fileRole);

      // Chunk-level enrichment via custom LLM — SERIALIZED per chunk (concurrency 1).
      // Mastra's SchemaExtractor fires one LLM call PER CHUNK in PARALLEL
      // (Promise.all over nodes), which guarantees 429s on a single-slot llama.cpp
      // backend for any file with >1 chunk. We therefore drive enrichment ourselves:
      // one chunk at a time, awaiting each result before starting the next.
      const enrichmentConfig = this.configService.getEnrichmentConfig();
      const summaryMaxWords = deriveSummaryMaxWords(enrichmentConfig.docMaxTokens);
      const maxOutputTokens = deriveEnrichmentMaxOutputTokens(enrichmentConfig.docMaxTokens);

      // The chunked nodes — this is the list enrichment stamps onto and the final
      // domain mapping reads from.
      const docDocs = document.getDocs();

      if (enrichmentConfig.enabled && enrichmentConfig.llmUrl && enrichmentConfig.apiKey) {
        this.logger.info('[enrichment] Attempting enrichment', {
          enabled: enrichmentConfig.enabled,
          llmUrl: 'present',
          apiKey: 'present',
          model: enrichmentConfig.llmModel,
          filePath,
        });

        try {
          const customLLM = LlmClientFactory.createCustomLlm({
            ...(enrichmentConfig as unknown as Parameters<typeof LlmClientFactory.createCustomLlm>[0]),
            maxOutputTokens,
          });

          if (!customLLM) {
            this.logger.warn('[enrichment] LLM creation returned null', {
              model: enrichmentConfig.llmModel,
              filePath,
            });
          } else {
            this.logger.info('[enrichment] LLM created', {
              model: enrichmentConfig.llmModel,
              filePath,
            });

            // One LLM call per chunk, strictly sequential. A failing chunk is left
            // un-enriched (after the corrective retry) and does not abort the rest.
            for (const chunk of docDocs) {
              await this.enrichChunk(
                chunk,
                customLLM,
                docType,
                filePath,
                sourceId,
                summaryMaxWords,
                enrichmentConfig.timeoutMs,
              );
            }

            // Verify enrichment was stored in chunk metadata under the 'enrichment' key
            const firstChunk = docDocs[0];
            const enrichmentData = firstChunk?.metadata?.enrichment as Record<string, unknown> | undefined;
            const hasTitle = typeof enrichmentData?.title === 'string';
            const hasKeywords = typeof enrichmentData?.keywords === 'string';
            const hasSummary = typeof enrichmentData?.summary === 'string';

            this.logger.info(
              `[enrichment] Extracted metadata; hasTitle=${hasTitle}, hasKeywords=${hasKeywords}, hasSummary=${hasSummary}`,
              {
                hasTitle,
                hasKeywords,
                hasSummary,
                filePath,
              },
            );
          }
        } catch (error) {
          // Non-fatal — log warning, continue without enrichment
          const err = error instanceof Error ? error : new Error(String(error));
          this.logger.warn('[enrichment] ExtractMetadata failed', {
            error: err.message,
            stack: err.stack ?? 'no stack',
            filePath,
          });
        }
      } else {
        // Determine skip reason for clarity
        let reason = 'unknown';
        if (!enrichmentConfig.enabled) {
          reason = 'enabled=false';
        } else if (!enrichmentConfig.llmUrl) {
          reason = 'missing llmUrl';
        } else if (!enrichmentConfig.apiKey) {
          reason = 'missing apiKey';
        }

        this.logger.info('[enrichment] Skipped', {
          reason,
          filePath,
        });
      }

      // Get chunks from MDocument using getDocs()
      const mastraChunks = docDocs;

      if (mastraChunks.length === 0) {
        return Result.ok([]);
      }

      // Map Mastra chunks to domain Chunk entities
      const chunks = this.mapToDomainChunks(mastraChunks, filePath, sourceId, fileRole);

      return Result.ok(chunks);
    } catch (error) {
      return Result.ko([
        new ErrorWithDetails(
          error instanceof Error ? error.message : 'Unknown error during Mastra chunking',
          'MastraChunkingError',
          { filePath, sourceId },
        ),
      ]);
    }
  }

  /**
   * Determine the chunker (markdown/recursive/json/sentence) based on file extension.
   */
  private determineStrategy(filePath: string): MastraChunkStrategy {
    const ext = this.getExtension(filePath).toLowerCase();
    const basename = filePath.split('/').pop()?.toLowerCase() ?? '';

    // Markdown
    if (['.md', '.mdx', '.markdown'].includes(ext)) {
      return 'markdown';
    }

    // HTML — use the markdown chunker (header-based splitting)
    if (['.html', '.htm'].includes(ext)) {
      return 'markdown';
    }

    // Code files — recursive chunking
    if (this.isCodeExtension(ext)) {
      return 'recursive';
    }

    // Config files — json chunker
    if (this.isConfigExtension(ext) || basename === '.env' || basename.startsWith('.env.')) {
      return 'json';
    }

    // Plain text — sentence-based
    if (['.txt', '.text', '.log'].includes(ext)) {
      return 'sentence';
    }

    // Fallback to sentence
    return 'sentence';
  }

  /**
   * Determine MDocument factory type based on file extension.
   */
  private determineDocumentType(filePath: string): MastraDocumentType {
    const ext = this.getExtension(filePath).toLowerCase();

    if (['.md', '.mdx', '.markdown'].includes(ext)) {
      return 'markdown';
    }

    if (['.json'].includes(ext)) {
      return 'json';
    }

    if (['.html', '.htm'].includes(ext)) {
      return 'html';
    }

    // Default to text for everything else (including yaml, code, etc.)
    return 'text';
  }

  /**
   * Determine file role based on file path and extension.
   */
  private determineFileRole(filePath: string): FileRole {
    const ext = this.getExtension(filePath).toLowerCase();

    // Config files
    if (this.isConfigExtension(ext)) {
      return FILE_ROLES.CONFIG;
    }

    // Code files
    if (this.isCodeExtension(ext)) {
      return FILE_ROLES.CODE;
    }

    // Default to docs
    return FILE_ROLES.DOCS;
  }

  /**
   * Create MDocument using type-aware factory.
   */
  private createDocument(
    content: string,
    docType: MastraDocumentType,
    filePath: string,
    sourceId: string,
  ): MDocument {
    const metadata = {
      filePath,
      sourceId,
    };

    switch (docType) {
      case 'markdown':
        return MDocument.fromMarkdown(content, metadata);
      case 'json':
        return MDocument.fromJSON(content, metadata);
      case 'html':
        return MDocument.fromHTML(content, metadata);
      case 'text':
      default:
        return MDocument.fromText(content, metadata);
    }
  }

  /**
   * Apply chunking to an MDocument with size limits from enhancement config.
   * No post-chunk truncation — Mastra handles splitting within limits natively.
   */
  private async applyChunking(
    document: MDocument,
    chunker: MastraChunkStrategy,
    fileRole: FileRole,
  ): Promise<void> {
    const maxChars = this.getMaxCharacters(fileRole);
    const minChars = Math.floor(maxChars * 0.5);
    const targetChars = Math.floor(maxChars * 0.75);
    // overlap must be < maxSize; use 25% of maxSize or 0 if too small
    const overlap = maxChars > 4 ? Math.floor(maxChars * 0.25) : 0;

    switch (chunker) {
      case 'markdown':
        // MarkdownTransformer: use maxSize per section
        await document.chunkMarkdown({ maxSize: maxChars, overlap });
        break;
      case 'recursive':
        // RecursiveCharacterTransformer: use maxSize
        await document.chunkRecursive({ maxSize: maxChars, overlap });
        break;
      case 'json':
        // RecursiveJsonTransformer: use maxSize + minSize
        await document.chunkJSON({ maxSize: maxChars, minSize: minChars });
        break;
      case 'sentence':
        // SentenceTransformer: use maxSize, minSize, targetSize
        await document.chunkSentence({
          maxSize: maxChars,
          minSize: minChars,
          targetSize: targetChars,
        });
        break;
    }
  }

  /**
   * Map Mastra chunks to domain Chunk entities.
   */
  private mapToDomainChunks(
    mastraChunks: { text: string; metadata?: Record<string, unknown> }[],
    filePath: string,
    sourceId: string,
    fileRole: FileRole,
  ): ContentChunk[] {
    const totalChunks = mastraChunks.length;
    const chunks: ContentChunk[] = [];

    for (let i = 0; i < mastraChunks.length; i++) {
      const mastraChunk = mastraChunks[i];
      const chunkMetadata = mastraChunk.metadata ?? {};

      // Build metadata record
      const metadata: Record<string, string> = {
        filePath,
        sourceId,
      };

      // Read enrichment from chunkMetadata.enrichment (schema-based extraction with metadataKey='enrichment')
      const enrichmentData = chunkMetadata.enrichment as Record<string, unknown> | undefined;
      const enrichmentTitle = typeof enrichmentData?.title === 'string' ? enrichmentData.title : undefined;
      const enrichmentKeywords =
        typeof enrichmentData?.keywords === 'string'
          ? truncateEnrichmentKeywords(enrichmentData.keywords)
          : undefined;
      const enrichmentSummary =
        typeof enrichmentData?.summary === 'string' ? enrichmentData.summary : undefined;

      if (enrichmentTitle) {
        metadata.mastraDocTitle = enrichmentTitle;
      }
      if (enrichmentKeywords) {
        metadata.mastraDocKeywords = enrichmentKeywords;
      }
      if (enrichmentSummary) {
        metadata.mastraDocSummary = enrichmentSummary;
      }

      const chunkResult = ContentChunk.of({
        id: generateId(),
        text: mastraChunk.text,
        chunkIndex: i,
        totalChunks,
        sectionHeader: enrichmentTitle || filePath,
        breadcrumb: filePath,
        fileRole,
        oversized: false,
        metadata,
        importance: 0.5,
        tags: [],
        memoryBank: 'default',
      });

      if (chunkResult.isOk()) {
        chunks.push(chunkResult.getValue());
      }
    }

    return chunks;
  }

  /**
   * Get file extension (lowercase).
   */
  private getExtension(filePath: string): string {
    const parts = filePath.split('.');
    return parts.length > 1 ? `.${parts[parts.length - 1]}` : '';
  }

  /**
   * Check if extension is a code file.
   */
  private isCodeExtension(ext: string): boolean {
    return [
      '.ts',
      '.tsx',
      '.js',
      '.jsx',
      '.py',
      '.go',
      '.java',
      '.rs',
      '.cs',
      '.php',
      '.rb',
      '.swift',
      '.kt',
      '.scala',
      '.cpp',
      '.c',
      '.h',
      '.hpp',
      '.m',
      '.mm',
      '.ex',
      '.exs',
      '.hs',
      '.pl',
      '.r',
      '.lua',
      '.dart',
      '.groovy',
    ].includes(ext);
  }

  /**
   * Check if extension is a config file.
   */
  private isConfigExtension(ext: string): boolean {
    return ['.json', '.yaml', '.yml', '.toml', '.xml', '.ini', '.cfg', '.conf'].includes(ext);
  }
}
