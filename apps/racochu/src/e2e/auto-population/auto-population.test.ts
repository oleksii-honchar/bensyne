/**
 * [E2E] Auto-Population on Startup
 *
 * Verifies that racochu auto-populates missing/empty memory banks on startup
 * via ForceReprocessService.autoPopulateSources(). Four scenarios:
 *
 * A. Fresh source — source with no tracked files → startup populates files,
 *    memories appear in bank.
 * B. Stub repair — file with stub rows (file row + chunk rows, no memories)
 *    → startup re-ingests and creates live memories.
 * C. Healthy source — source with live memories → startup skips, no
 *    re-ingestion (memory count unchanged).
 * D. Opt-out — source with autoPopulate: false → startup skips, files not
 *    ingested.
 */

import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as path from 'path';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { ForceReprocessService } from '../../application/services/force-reprocess.service';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { createTestApplication } from '../main.test-application';

// Wait for debounce(500ms) + chunking + MCP ingestion + Mnemosyne indexing.
const PROCESSING_WAIT_MS = 20000;

describe('[E2E] Auto-Population on Startup', () => {
  let app: INestApplication | null = null;
  let forceReprocessService: ForceReprocessService | null = null;
  let bensyneClient: BensyneClient | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let watchDir: string | undefined;
  let memoryBank: string | undefined;
  let sources: ReturnType<ConfigurationService['getWatchSources']> | undefined;

  beforeAll(async () => {
    watchDir = process.env.E2E_WATCH_DIR;
    if (!watchDir) {
      throw new Error('E2E_WATCH_DIR not set');
    }

    console.log(`[E2E-AutoPopulate] Watch directory: ${watchDir}`);

    app = await createTestApplication();
    await app.init();

    const configService = app.get(ConfigurationService);
    sources = configService.getWatchSources();
    const source = sources.find(s => s.id === 'e2e-test-source');
    expect(source).toBeDefined();
    memoryBank = source!.memoryBank;

    console.log(`[E2E-AutoPopulate] Memory bank: ${memoryBank}`);

    forceReprocessService = app.get(ForceReprocessService);
    bensyneClient = app.get(BensyneClient);
    processingQueue = app.get(FileProcessingQueue);
  }, 90000);

  afterAll(async () => {
    if (app) {
      await app.close().catch(() => undefined);
    }
  });

  /** Create a unique test file with distinctive content. */
  async function createTestFile(name: string, content: string): Promise<string> {
    const filePath = path.join(watchDir!, name);
    await fs.writeFile(filePath, content, 'utf-8');
    return filePath;
  }

  /** Verify a file has memories in the bank (via recall). */
  async function fileHasMemories(filePath: string, marker: string) {
    const result = await bensyneClient!.recall(marker, 3, 2000, memoryBank!);
    expect(result.isOk()).toBe(true);
    const results = result.getValue();
    const hasFile = results.some(r => r.content.includes(marker));
    return hasFile;
  }

  /** Count chunks for a file via getFileChunks. */
  async function getFileChunkCount(filePath: string): Promise<number> {
    const result = await bensyneClient!.getFileChunks(filePath, memoryBank!);
    expect(result.isOk()).toBe(true);
    const info = result.getValue();
    return info.chunks.length;
  }

  it('Scenario A: fresh source auto-populates, memories appear in bank', async () => {
    const uniqueId = `auto-a-${Date.now()}`;
    const marker = `AUTOPOP-A-${uniqueId}`;
    const fileName = `${uniqueId}.md`;
    const content = `# Auto-Populate Test A ${uniqueId}\n\nThis is a test file for auto-population scenario A.\n\nMarker: ${marker}\n\nThis file was never ingested before. Auto-population should detect it and ingest it on startup.`;

    const filePath = await createTestFile(fileName, content);
    console.log(`[E2E-AutoPopulate-A] Created fresh file: ${filePath}`);

    // Verify no memories yet.
    let hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(false);

    // Run auto-populate on this source only.
    console.log('[E2E-AutoPopulate-A] Running autoPopulateSources...');
    await forceReprocessService!.autoPopulateSources(sources!);

    // Wait for processing queue to drain.
    console.log('[E2E-AutoPopulate-A] Waiting for processing queue...');
    await processingQueue!.waitForEmpty();
    await new Promise(r => setTimeout(r, PROCESSING_WAIT_MS));

    // Verify memories now exist.
    console.log('[E2E-AutoPopulate-A] Verifying memories...');
    hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(true);

    // Verify file chunks exist in bank.
    const chunkCount = await getFileChunkCount(filePath);
    expect(chunkCount).toBeGreaterThan(0);

    console.log(`[E2E-AutoPopulate-A] SUCCESS: fresh source auto-populated, ${chunkCount} chunks in bank`);
  }, 180000);

  it('Scenario B: untracked file re-ingested via auto-population', async () => {
    // This simulates "stub repair" at the racochu level: a file that has
    // been forgotten (all memories deleted) but still has a file row is
    // detected as untracked and re-ingested.
    const uniqueId = `auto-b-${Date.now()}`;
    const marker = `AUTOPOP-B-${uniqueId}`;
    const fileName = `${uniqueId}.md`;
    const content = `# Auto-Populate Test B ${uniqueId}\n\nThis is a test file for auto-population scenario B.\n\nMarker: ${marker}\n\nThis file will be ingested, then forgotten, then re-ingested by auto-population.`;

    const filePath = await createTestFile(fileName, content);
    console.log(`[E2E-AutoPopulate-B] Created file: ${filePath}`);

    // Ingest the file first (via processFileUseCase through the service).
    console.log('[E2E-AutoPopulate-B] Initial ingestion...');
    await forceReprocessService!.forceReprocessSource('e2e-test-source', sources!);
    await processingQueue!.waitForEmpty();
    await new Promise(r => setTimeout(r, PROCESSING_WAIT_MS));

    // Verify memories exist.
    let hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(true);

    // Now forget the file (simulates "stub rows" — all memories deleted).
    console.log('[E2E-AutoPopulate-B] Forgetting file (simulating stub rows)...');
    const forgetResult = await bensyneClient!.forgetByFile(filePath, memoryBank!);
    expect(forgetResult.isOk()).toBe(true);
    console.log(`[E2E-AutoPopulate-B] Forget result: ${JSON.stringify(forgetResult.getValue())}`);

    // Verify memories are gone.
    hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(false);

    // Run auto-populate — it should detect the untracked file and re-ingest.
    console.log('[E2E-AutoPopulate-B] Running autoPopulateSources...');
    await forceReprocessService!.autoPopulateSources(sources!);
    await processingQueue!.waitForEmpty();
    await new Promise(r => setTimeout(r, PROCESSING_WAIT_MS));

    // Verify memories are restored.
    console.log('[E2E-AutoPopulate-B] Verifying memories restored...');
    hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(true);

    const chunkCount = await getFileChunkCount(filePath);
    expect(chunkCount).toBeGreaterThan(0);

    console.log(`[E2E-AutoPopulate-B] SUCCESS: untracked file re-ingested, ${chunkCount} chunks restored`);
  }, 300000);

  it('Scenario C: healthy file skipped by auto-population (no re-ingestion)', async () => {
    const uniqueId = `auto-c-${Date.now()}`;
    const marker = `AUTOPOP-C-${uniqueId}`;
    const fileName = `${uniqueId}.md`;
    const content = `# Auto-Populate Test C ${uniqueId}\n\nThis is a test file for auto-population scenario C.\n\nMarker: ${marker}\n\nThis file has healthy memories — auto-population should skip it.`;

    const filePath = await createTestFile(fileName, content);
    console.log(`[E2E-AutoPopulate-C] Created file: ${filePath}`);

    // Ingest the file.
    console.log('[E2E-AutoPopulate-C] Initial ingestion...');
    await forceReprocessService!.forceReprocessSource('e2e-test-source', sources!);
    await processingQueue!.waitForEmpty();
    await new Promise(r => setTimeout(r, PROCESSING_WAIT_MS));

    // Verify memories exist.
    let hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(true);

    // Record chunk count before auto-populate.
    const chunksBefore = await getFileChunkCount(filePath);
    console.log(`[E2E-AutoPopulate-C] Chunks before auto-populate: ${chunksBefore}`);

    // Run auto-populate — should skip this healthy file.
    console.log('[E2E-AutoPopulate-C] Running autoPopulateSources...');
    await forceReprocessService!.autoPopulateSources(sources!);
    await processingQueue!.waitForEmpty();
    await new Promise(r => setTimeout(r, 5000));

    // Verify memories still exist and chunk count unchanged.
    hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(true);

    const chunksAfter = await getFileChunkCount(filePath);
    expect(chunksAfter).toBe(chunksBefore);

    console.log(
      `[E2E-AutoPopulate-C] SUCCESS: healthy file skipped, chunk count unchanged (${chunksBefore})`,
    );
  }, 240000);

  it('Scenario D: source with autoPopulate: false is not auto-populated', async () => {
    // Create a separate directory for the opt-out source.
    const optOutDir = path.join(path.dirname(watchDir!), 'auto-populate-optout');
    await fs.mkdir(optOutDir, { recursive: true });

    const uniqueId = `auto-d-${Date.now()}`;
    const marker = `AUTOPOP-D-${uniqueId}`;
    const fileName = `${uniqueId}.md`;
    const content = `# Auto-Populate Test D ${uniqueId}\n\nThis is a test file for auto-population scenario D.\n\nMarker: ${marker}\n\nThis source has autoPopulate: false — file should NOT be ingested.`;

    const filePath = path.join(optOutDir, fileName);
    await fs.writeFile(filePath, content, 'utf-8');
    console.log(`[E2E-AutoPopulate-D] Created file in opt-out source: ${filePath}`);

    // Configure an opt-out source.
    const optOutSource = {
      id: 'e2e-opt-out-source',
      path: optOutDir,
      exclude: [],
      debounceMs: 500,
      memoryBank: memoryBank!,
      autoPopulate: false,
    };

    // Run auto-populate on the opt-out source only.
    console.log('[E2E-AutoPopulate-D] Running autoPopulateSources on opt-out source...');
    await forceReprocessService!.autoPopulateSources([optOutSource]);
    await processingQueue!.waitForEmpty();
    await new Promise(r => setTimeout(r, 5000));

    // Verify file was NOT ingested (no memories).
    console.log('[E2E-AutoPopulate-D] Verifying file was NOT ingested...');
    const hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(false);

    // Verify no chunks in bank.
    const chunkCount = await getFileChunkCount(filePath);
    expect(chunkCount).toBe(0);

    console.log('[E2E-AutoPopulate-D] SUCCESS: opt-out source not auto-populated');

    // Clean up opt-out directory.
    await fs.rm(optOutDir, { recursive: true, force: true });
  }, 120000);
});