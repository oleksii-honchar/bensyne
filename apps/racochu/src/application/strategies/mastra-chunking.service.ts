import { LlmClientFactory } from '@/application/services/llm-client-factory';
import { ContentChunk, FILE_ROLES, FileRole } from '@/domain/content-chunk.entity';
import { ConfigurationService } from '@/infrastructure/config/configuration.service';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { generateId } from '@/utils/big-endian-id';
import { ErrorWithDetails } from '@/utils/error-with-details';
import { Result } from '@/utils/result';
import { MDocument } from '@mastra/rag';
import { Injectable } from '@nestjs/common';
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

      // Document-level enrichment via custom LLM
      let enrichedDoc = document;
      const enrichmentConfig = this.configService.getEnrichmentConfig();
      const summaryMaxWords = deriveSummaryMaxWords(enrichmentConfig.docMaxTokens);

      if (enrichmentConfig.enabled && enrichmentConfig.llmUrl && enrichmentConfig.apiKey) {
        this.logger.info('[enrichment] Attempting enrichment', {
          enabled: enrichmentConfig.enabled,
          llmUrl: 'present',
          apiKey: 'present',
          model: enrichmentConfig.llmModel,
          filePath,
        });

        try {
          const customLLM = LlmClientFactory.createCustomLlm(
            enrichmentConfig as Parameters<typeof LlmClientFactory.createCustomLlm>[0],
          );

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

            enrichedDoc = await document.extractMetadata({
              schema: {
                schema: MastraChunkingService.enrichmentSchema,
                llm: customLLM,
                instructions: `You must respond ONLY with valid JSON.

Extract the following fields from the document:
- title: A concise title describing the content
- keywords: Comma-separated keywords
- summary: A concise whole-file summary of the document, at most ${summaryMaxWords} words

Respond in this format:
{
  "title": "string",
  "keywords": "keyword1, keyword2, keyword3"
}

Do not include any other text, explanations, or markdown formatting.`,
                metadataKey: 'enrichment',
              },
            });

            // Verify enrichment was stored in chunk metadata under the 'enrichment' key
            const docDocs = enrichedDoc.getDocs();
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
      const mastraChunks = enrichedDoc.getDocs();

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
        typeof enrichmentData?.keywords === 'string' ? enrichmentData.keywords : undefined;
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
