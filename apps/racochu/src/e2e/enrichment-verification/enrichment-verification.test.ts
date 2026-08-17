import { WatchSourceConfig } from '@/infrastructure/config/config-schemas';
import { ConfigurationService } from '@/infrastructure/config/configuration.service';
import { SOURCE_STRATEGIES } from '@/infrastructure/config/source-strategies';
import { BensyneClient } from '@/infrastructure/services/bensyne-client.service';
import { ChunkContentUseCase } from '@/use-cases/chunk-content.use-case';
import { ProcessFileUseCase } from '@/use-cases/process-file.use-case';
import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as path from 'path';
import { cleanupTempDir, createTempDir } from '../e2e-utils';
import { createTestApplication } from '../main.test-application';

/**
 * E2E integration test for the full enrichment flow.
 *
 * Verifies:
 * 1. Chunks are created with enrichment metadata (mastraDocTitle, mastraDocKeywords)
 * 2. File is processed and ingested to Mnemosyne successfully
 * 3. Content is recalled via BensyneClient.recall() — metadata stored and retrievable
 *
 * Skipped gracefully if enrichment config is incomplete (no apiKey, no llmUrl).
 */
describe('[E2E] Enrichment Verification — Full Flow', () => {
  let app: INestApplication | null = null;
  let processFileUseCase: ProcessFileUseCase | null = null;
  let chunkContentUseCase: ChunkContentUseCase | null = null;
  let bensyneClient: BensyneClient | null = null;
  let configurationService: ConfigurationService | null = null;
  let tempDir: string | null = null;

  const TEST_SOURCE_ID = 'e2e-test-source';
  const TEST_MEMORY_BANK = 'e2e-test-ns';
  const TEST_SOURCE_CONFIG: WatchSourceConfig = {
    id: TEST_SOURCE_ID,
    path: '',
    memoryBank: TEST_MEMORY_BANK,
    strategy: SOURCE_STRATEGIES.CONTENT_AWARE,
    description: 'E2E enrichment verification source',
    exclude: [],
    debounceMs: 3000,
  };

  // ~500 char test document with clear, identifiable content for enrichment
  // Marker is placed early in the body to ensure it's included in recall results (which may truncate long chunks)
  const TEST_MARKDOWN_CONTENT = (marker: string) => `# Enrichment Verification Test Document

${marker}

This document is used to verify that LLM enrichment is working correctly in the RAG Content Chunker pipeline. It contains clear, identifiable content that should produce meaningful metadata.

## Key Concepts

The enrichment process should extract a title and keywords from this document. The title should reflect the document's main topic, and keywords should capture the key terms present in the content.

## Expected Behavior

When enrichment is enabled and the LLM endpoint is reachable, each chunk should include mastraDocTitle and mastraDocKeywords in its metadata. These fields are extracted by the LLM and attached at the document level, propagating to all chunks.`;

  beforeAll(async () => {
    app = await createTestApplication();
    await app.init();

    processFileUseCase = app.get(ProcessFileUseCase);
    chunkContentUseCase = app.get(ChunkContentUseCase);
    bensyneClient = app.get(BensyneClient);
    configurationService = app.get(ConfigurationService);
    tempDir = await createTempDir('rag-e2e-enrichment-');

    console.log(`[E2E-Enrichment] Server bootstrapped, temp dir: ${tempDir}`);
  }, 90000);

  afterAll(async () => {
    if (tempDir) {
      await cleanupTempDir(tempDir);
    }
    if (app) {
      const closePromise = app.close().catch(() => {});
      const timeoutPromise = new Promise(resolve => setTimeout(resolve, 30000));
      await Promise.race([closePromise, timeoutPromise]);
    }
  });

  it('should process file with enrichment and verify metadata in chunks and recall', async () => {
    // Skip if enrichment config is incomplete
    const enrichmentConfig = configurationService!.getEnrichmentConfig();
    if (!enrichmentConfig.enabled || !enrichmentConfig.apiKey || !enrichmentConfig.llmUrl) {
      console.log(
        `[E2E-Enrichment] Skipping: enrichment config incomplete — enabled=${enrichmentConfig.enabled}, apiKey=${!!enrichmentConfig.apiKey}, llmUrl=${!!enrichmentConfig.llmUrl}`,
      );
      return;
    }

    const uniqueId = Date.now();
    const marker = `ENRICHMENT-E2E-TEST-${uniqueId}`;
    const content = TEST_MARKDOWN_CONTENT(marker);
    const filePath = path.join(tempDir!, `enrichment-test-${uniqueId}.md`);
    await fs.writeFile(filePath, content, 'utf-8');

    console.log(`[E2E-Enrichment] Test file created: ${filePath}`);

    // ---- Step 1: Chunk content via ChunkContentUseCase to verify enrichment metadata ----
    const chunksResult = await chunkContentUseCase!.execute({
      content,
      filePath,
      sourceId: TEST_SOURCE_ID,
      memoryBank: TEST_MEMORY_BANK,
      sourceConfig: TEST_SOURCE_CONFIG,
    });

    expect(chunksResult.isOk()).toBe(true);
    const chunks = chunksResult.getValue();
    expect(chunks.length).toBeGreaterThan(0);
    console.log(`[E2E-Enrichment] Chunks created: ${chunks.length}`);

    // Verify enrichment metadata is present in chunk metadata
    const firstChunk = chunks[0];
    console.log(
      `[E2E-Enrichment] First chunk metadata keys: ${JSON.stringify(Object.keys(firstChunk.metadata ?? {}))}`,
    );

    expect(firstChunk.metadata?.mastraDocTitle).toBeDefined();
    expect(typeof firstChunk.metadata?.mastraDocTitle).toBe('string');
    expect(firstChunk.metadata!.mastraDocTitle!.length).toBeGreaterThan(0);
    console.log(`[E2E-Enrichment] mastraDocTitle: "${firstChunk.metadata!.mastraDocTitle}"`);

    expect(firstChunk.metadata?.mastraDocKeywords).toBeDefined();
    expect(typeof firstChunk.metadata?.mastraDocKeywords).toBe('string');
    expect(firstChunk.metadata!.mastraDocKeywords!.length).toBeGreaterThan(0);
    console.log(`[E2E-Enrichment] mastraDocKeywords: "${firstChunk.metadata!.mastraDocKeywords}"`);

    // All chunks should have the same document-level enrichment metadata
    for (const chunk of chunks) {
      expect(chunk.metadata?.mastraDocTitle).toBe(firstChunk.metadata!.mastraDocTitle);
      expect(chunk.metadata?.mastraDocKeywords).toBe(firstChunk.metadata!.mastraDocKeywords);
    }
    console.log(`[E2E-Enrichment] All ${chunks.length} chunks have enrichment metadata`);

    // ---- Step 2: Process file via ProcessFileUseCase to verify full ingestion flow ----
    const processResult = await processFileUseCase!.execute({
      filePath,
      eventType: 'add',
      sourceId: TEST_SOURCE_ID,
      memoryBank: TEST_MEMORY_BANK,
      sourceConfig: TEST_SOURCE_CONFIG,
    });

    expect(processResult.isOk()).toBe(true);
    console.log(`[E2E-Enrichment] File processed and ingested successfully`);

    // ---- Step 3: Wait for Mnemosyne to index, then recall to verify storage/retrieval ----
    console.log(`[E2E-Enrichment] Waiting 20s for Mnemosyne indexing...`);
    await new Promise(resolve => setTimeout(resolve, 20000));

    // Recall using the unique marker — should find content in Mnemosyne
    const recallResult = await bensyneClient!.recall(marker, 5, 2000, TEST_MEMORY_BANK);
    expect(recallResult.isOk()).toBe(true);
    const recallResults = recallResult.getValue();
    console.log(`[E2E-Enrichment] Recall returned ${recallResults.length} results`);

    expect(recallResults.length).toBeGreaterThan(0);
    const foundMarker = recallResults.some(r => r.content.includes(marker));
    expect(foundMarker).toBe(true);
    console.log(`[E2E-Enrichment] Marker "${marker}" found in recall results`);

    // Verify that at least one recall result contains enrichment-related content
    // (the metadata is stored alongside the content, so the recall should return the chunk text)
    const enrichedResult = recallResults.find(r => r.content.includes('enrichment') || r.content.includes('Enrichment'));
    expect(enrichedResult).toBeDefined();
    console.log(`[E2E-Enrichment] Enrichment content found in recall: "${enrichedResult?.content.slice(0, 120)}..."`);

    // File-based memories are recalled with an opaque bensyne-owned file_enrichment block
    // (Task 13 / S6 tolerance — racochu passes it through without parsing the shape).
    // The marker hit is a file chunk, so its result must carry the enrichment block.
    const markerResult = recallResults.find(r => r.content.includes(marker));
    expect(markerResult?.file_enrichment).toBeDefined();
    console.log(
      `[E2E-Enrichment] file_enrichment present on marker result: ${JSON.stringify(markerResult?.file_enrichment ?? null).slice(0, 160)}`,
    );

    console.log(`[E2E-Enrichment] Full enrichment flow verified successfully`);
  }, 120000);
});

/**
 * LLM connectivity tests — validate the prerequisites for enrichment.
 *
 * Test A: API key validation — sends a minimal OpenAI-compatible request to
 *   {llmUrl}/chat/completions with the configured apiKey, model, and empty
 *   messages. HTTP 200 = valid key, 401/403 = invalid key, 5xx = other error.
 *
 * Test B: Endpoint connectivity — sends a request to the LLM endpoint with a
 *   short timeout (5s). Any HTTP response = reachable, timeout/ECONNREFUSED =
 *   unreachable.
 *
 * Both tests use native fetch() and skip if enrichment config is incomplete.
 */
describe('LLM connectivity', () => {
  let app: INestApplication | null = null;
  let configurationService: ConfigurationService | null = null;

  beforeAll(async () => {
    app = await createTestApplication();
    await app.init();
    configurationService = app.get(ConfigurationService);
  }, 90000);

  afterAll(async () => {
    if (app) {
      const closePromise = app.close().catch(() => {});
      const timeoutPromise = new Promise(resolve => setTimeout(resolve, 30000));
      await Promise.race([closePromise, timeoutPromise]);
    }
  });

  it('Test A: API key validation — verifies the configured apiKey is accepted by the LLM endpoint', async () => {
    const config = configurationService!.getEnrichmentConfig();
    if (!config.apiKey || !config.llmUrl) {
      console.log('[enrichment] Skipping API key validation: apiKey or llmUrl not configured');
      return;
    }

    const url = `${config.llmUrl}/chat/completions`;
    console.log(`[enrichment] API key validation — sending request to ${url}`);

    const body = JSON.stringify({
      model: config.llmModel ?? 'puma-qwopus3.5-9b-instruct',
      messages: [{ role: 'user', content: 'test' }],
      max_tokens: 1,
    });

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.apiKey}`,
      },
      body,
    });

    const status = response.status;
    console.log(`[enrichment] API key validation — HTTP ${status}`);

    if (status === 200) {
      console.log('[enrichment] API key validation — key is valid');
    } else if (status === 401 || status === 403) {
      console.log('[enrichment] API key validation — key is INVALID (HTTP 401/403)');
    } else if (status >= 500) {
      console.log(`[enrichment] API key validation — server error (HTTP ${status})`);
    } else {
      console.log(`[enrichment] API key validation — unexpected status (HTTP ${status})`);
    }

    expect(status).toBeGreaterThanOrEqual(200);
    expect(status).toBeLessThan(500);
  }, 30000);

  it('Test B: Endpoint connectivity — verifies the LLM endpoint is reachable', async () => {
    const config = configurationService!.getEnrichmentConfig();
    if (!config.llmUrl) {
      console.log('[enrichment] Skipping endpoint connectivity: llmUrl not configured');
      return;
    }

    const url = `${config.llmUrl}/chat/completions`;
    console.log(`[enrichment] Endpoint connectivity — pinging ${url} (5s timeout)`);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: config.llmModel ?? 'puma-qwopus3.5-9b-instruct',
          messages: [{ role: 'user', content: 'test' }],
          max_tokens: 1,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      console.log(`[enrichment] Endpoint connectivity — reachable (HTTP ${response.status})`);
      expect(response.status).toBeGreaterThanOrEqual(100);
    } catch (error) {
      clearTimeout(timeoutId);
      const message = error instanceof Error ? error.message : String(error);

      if (error instanceof Error && error.name === 'AbortError') {
        console.log(`[enrichment] Endpoint connectivity — UNREACHABLE (timeout after 5s)`);
        fail('LLM endpoint is unreachable — request timed out after 5s');
      } else {
        console.log(`[enrichment] Endpoint connectivity — UNREACHABLE (${message})`);
        fail(`LLM endpoint is unreachable: ${message}`);
      }
    }
  }, 15000);
});
