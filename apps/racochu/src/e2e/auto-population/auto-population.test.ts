/**
 * [E2E] Auto-Population on Startup
 *
 * Verifies that racochu auto-populates missing/empty memory banks on startup
 * via ForceReprocessService.autoPopulateSources(). Four scenarios:
 *
 * A. Boot-time discovery — files already present in the source when the app
 *    boots → the startup auto-populate pass discovers them; memories appear in
 *    bank. The fixture lives in a PRIVATE UNWATCHED dir materialized BEFORE
 *    app boot and is passed to autoPopulateSources() as an explicit scoped
 *    source (same pattern as Scenario D), so no live FileWatcher ever observes
 *    it and the "already present at boot, not yet ingested" precondition is
 *    race-free by construction.
 * A2. Second-run re-baseline (DEC-A7, spec §8) — the SAME scoped source is
 *    auto-populated again after A's full first pass: the queue is
 *    new-files-only, the fixture now has a FileTracker row ⇒ the returned
 *    summary DATA is all zero (files=0 — the healthy repeat-run signature,
 *    structural via row-subtraction, not gate-dependent) and the bank state
 *    is untouched.
 * B. Lost-in-bank repair ownership (RE-BASELINED per DEC-A7) — a file whose
 *    row remains while its bank content is forgotten is NOT repaired by
 *    auto-populate any more (the new-files-only queue excludes every file
 *    with a row — bank verification retired from resume); the scenario proves
 *    the ownership move end-to-end: auto-populate leaves it untouched, then
 *    --recover (the mode that owns guarantee (a)) restores it.
 * C. Healthy source — source with live memories → startup skips, no
 *    re-ingestion (memory count unchanged).
 * D. Opt-out — source with autoPopulate: false → startup skips, files not
 *    ingested.
 */

import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as path from 'path';
import { DEFAULT_CONTENT_FILTER_OPTIONS } from '../../application/services/content-classifier.service';
import { ForceReprocessService } from '../../application/services/force-reprocess.service';
import { RecoverService } from '../../application/services/recover.service';
import type { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { SOURCE_TYPES } from '../../infrastructure/config/source-types';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { createTestApplication } from '../main.test-application';

// Wait for debounce(500ms) + chunking + MCP ingestion + Mnemosyne indexing.
const PROCESSING_WAIT_MS = 20000;

describe('[E2E] Auto-Population on Startup', () => {
  let app: INestApplication | null = null;
  let forceReprocessService: ForceReprocessService | null = null;
  let recoverService: RecoverService | null = null;
  let bensyneClient: BensyneClient | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let watchDir: string | undefined;
  let memoryBank: string | undefined;
  let sources: ReturnType<ConfigurationService['getWatchSources']> | undefined;
  // Scenario A fixture — created BEFORE the app boots, in a directory that is
  // not a configured watch source (see beforeAll).
  let bootFixtureDir: string | undefined;
  let bootFixtureFilePath: string | undefined;
  let bootFixtureMarker: string | undefined;
  // Scenario A2 (DEC-A7 second-run re-baseline) — shared with Scenario A
  // across the two sequential tests (maxWorkers: 1).
  let bootSource: WatchSourceConfig | null = null;
  let bootFixtureChunksAfterFirstPass = -1;

  beforeAll(async () => {
    watchDir = process.env.E2E_WATCH_DIR;
    if (!watchDir) {
      throw new Error('E2E_WATCH_DIR not set');
    }

    console.log(`[E2E-AutoPopulate] Watch directory: ${watchDir}`);

    // Scenario A fixture must already exist at app boot. It materializes in a
    // dedicated sibling directory under the e2e temp root that is NOT part of
    // the config's watchSources — FileWatcherService only ever watches
    // configured sources (onApplicationBootstrap → start() over
    // getWatchSources()), so this directory is never live-watched. The
    // scenario passes it to autoPopulateSources() explicitly as a scoped
    // source (Scenario D pattern), which is what production does at watch
    // start — boot-time discovery, with no watcher that could race the test.
    bootFixtureDir = path.join(path.dirname(watchDir), 'auto-populate-boot');
    await fs.rm(bootFixtureDir, { recursive: true, force: true });
    await fs.mkdir(bootFixtureDir, { recursive: true });

    const bootId = `auto-a-${Date.now()}`;
    bootFixtureMarker = `AUTOPOP-A-${bootId}`;
    bootFixtureFilePath = path.join(bootFixtureDir, `${bootId}.md`);
    await fs.writeFile(
      bootFixtureFilePath,
      `# Auto-Populate Test A ${bootId}\n\nThis is a test file for auto-population scenario A.\n\nMarker: ${bootFixtureMarker}\n\nThis file was never ingested before. It exists when the app boots — auto-population should detect it and ingest it on startup.`,
      'utf-8',
    );
    console.log(`[E2E-AutoPopulate-A] Pre-boot fixture materialized (unwatched dir): ${bootFixtureFilePath}`);

    app = await createTestApplication();
    await app.init();

    const configService = app.get(ConfigurationService);
    sources = configService.getWatchSources();
    const source = sources.find(s => s.id === 'e2e-test-source');
    expect(source).toBeDefined();
    memoryBank = source!.memoryBank;

    console.log(`[E2E-AutoPopulate] Memory bank: ${memoryBank}`);

    forceReprocessService = app.get(ForceReprocessService);
    recoverService = app.get(RecoverService);
    bensyneClient = app.get(BensyneClient);
    processingQueue = app.get(FileProcessingQueue);
  }, 90000);

  afterAll(async () => {
    // Lifecycle verified (Ad-Hoc A): app.close() runs GracefulShutdownService
    // → FileWatcherService.onApplicationShutdown() → stop(), closing every
    // chokidar watcher before the next suite starts in the shared jest process
    // (observed as "Stopped watching source" lines after each run).
    if (app) {
      await app.close().catch(() => undefined);
    }
    if (bootFixtureDir) {
      await fs.rm(bootFixtureDir, { recursive: true, force: true }).catch(() => undefined);
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

  it('Scenario A: files present before boot are discovered by auto-populate at startup', async () => {
    // Intent preserved: boot-time discovery of PRE-EXISTING files. The fixture
    // existed before app.init() (beforeAll) and lives in an unwatched dir, so
    // the only code path that could ever ingest it is the scoped
    // auto-populate pass invoked below — the "no memories yet" precondition
    // and the after-the-fact discovery are both race-free by construction.
    const filePath = bootFixtureFilePath!;
    const marker = bootFixtureMarker!;

    // Sanity: the fixture is on disk BEFORE the startup pass runs (it was
    // materialized before the app booted).
    const stat = await fs.stat(filePath);
    expect(stat.isFile()).toBe(true);

    // This dir is not in the config's watch sources — pass it as an explicit
    // scoped source. Field shape mirrors Scenario D (resolved-config required
    // props at schema defaults); autoPopulate stays true (the default — this
    // scenario is the opt-IN path).
    bootSource = {
      id: 'e2e-autopop-boot-source',
      path: bootFixtureDir!,
      resolvedPaths: [bootFixtureDir!],
      exclude: [],
      debounceMs: 500,
      memoryBank: memoryBank!,
      sourceType: SOURCE_TYPES.VAULT,
      contentFilter: DEFAULT_CONTENT_FILTER_OPTIONS,
      autoPopulate: true,
    };

    // Verify no memories yet — structurally guaranteed: the file is untracked
    // and no FileWatcher in this process has ever observed its directory.
    let hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(false);

    // Simulated startup auto-populate over the pre-populated source only
    // (main.ts watch-start order: scoped auto-populate before any watcher
    // would see it — here, without any watcher at all for this dir).
    console.log('[E2E-AutoPopulate-A] Running autoPopulateSources (scoped; fixture pre-existed boot)...');
    const summary = await forceReprocessService!.autoPopulateSources([bootSource]);

    // The pass itself must report discovering and ingesting the pre-existing
    // file. Counts are EXACT by construction: a private single-file source
    // is visible only to this call (never-ingestable precedent — stronger
    // than "≥1", same observable).
    expect(summary).toMatchObject({
      files: 1,
      gatedSkips: 0,
      terminalSkipSkips: 0,
      verifiedSkips: 0,
      reIngested: 1,
    });

    // Wait for processing queue to drain (bank-side visibility).
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
    bootFixtureChunksAfterFirstPass = chunkCount;

    console.log(
      `[E2E-AutoPopulate-A] SUCCESS: pre-existing file discovered by boot-time auto-populate, ${chunkCount} chunks in bank`,
    );
  }, 180000);

  it('Scenario A2 (DEC-A7 re-baseline): second auto-populate over the same scope queues nothing — all-zero summary, bank untouched', async () => {
    // Spec §8 re-baseline per DEC-A7 (AMENDED 2026-11-02): resume/auto-populate
    // queues NEW FILES ONLY. Scenario A's fixture now has a FileTracker row,
    // so the row-subtraction queue is EMPTY up front — files=0 is structural,
    // not gate-dependent. Asserted on the returned DATA (no log scraping).
    expect(bootSource).not.toBeNull();
    console.log('[E2E-AutoPopulate-A2] Running second autoPopulateSources over the SAME scope...');
    const summary = await forceReprocessService!.autoPopulateSources([bootSource!]);
    await processingQueue!.waitForEmpty();

    expect(summary).toEqual({
      files: 0,
      gatedSkips: 0,
      terminalSkipSkips: 0,
      verifiedSkips: 0,
      reIngested: 0,
    });

    // Bank observation: a known file never enters the pipeline — the chunks
    // created by A's first pass are exactly unchanged (zero churn).
    const chunksAfter = await getFileChunkCount(bootFixtureFilePath!);
    expect(chunksAfter).toBe(bootFixtureChunksAfterFirstPass);
    expect(chunksAfter).toBeGreaterThan(0);

    console.log(
      `[E2E-AutoPopulate-A2] SUCCESS: second pass all-zero (files=0, queue structurally empty), bank chunks unchanged (${chunksAfter})`,
    );
  }, 120000);

  it('Scenario B (DEC-A7 re-baseline): known file with lost bank content is NOT repaired by auto-populate — --recover restores it', async () => {
    // Pre-DEC-A7 this scenario proved auto-populate repairing a zero-bank
    // known file. The amended contract moves that duty: resume/auto-populate
    // queues NEW FILES ONLY — a file WITH a row is known and never re-enters
    // this path; lost-in-bank repair is --recover's guarantee (a). The
    // scenario now proves the ownership move: auto-populate no-op, recover
    // repair, same fixture.
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

    // Amended contract (DEC-A7): the file has a FileTracker row, so the
    // new-files-only queue excludes it — auto-populate must NOT re-ingest.
    // The file is known; zero work, zero repair (bank-verification retired
    // from resume).
    console.log('[E2E-AutoPopulate-B] Running autoPopulateSources (re-baselined: expects NO repair)...');
    await forceReprocessService!.autoPopulateSources(sources!);
    await processingQueue!.waitForEmpty();
    await new Promise(r => setTimeout(r, PROCESSING_WAIT_MS));

    hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(false);
    expect(await getFileChunkCount(filePath)).toBe(0);
    console.log('[E2E-AutoPopulate-B] Known file untouched by auto-populate (duty moved to --recover)');

    // The owner of lost-in-bank repair (guarantee (a)) — --recover — must
    // restore it: recover step 4 sees FILE_NOT_FOUND on the bank side and
    // force-ingests despite the unchanged hash.
    console.log('[E2E-AutoPopulate-B] Running recoverSource (the owning mode)...');
    await recoverService!.recoverSource('e2e-test-source', sources!);
    await processingQueue!.waitForEmpty();
    await new Promise(r => setTimeout(r, PROCESSING_WAIT_MS));

    // Verify memories are restored.
    console.log('[E2E-AutoPopulate-B] Verifying memories restored by --recover...');
    hasMemories = await fileHasMemories(filePath, marker);
    expect(hasMemories).toBe(true);

    const chunkCount = await getFileChunkCount(filePath);
    expect(chunkCount).toBeGreaterThan(0);

    console.log(
      `[E2E-AutoPopulate-B] SUCCESS: auto-populate skipped the known file (by design), --recover repaired it, ${chunkCount} chunks restored`,
    );
  }, 420000);

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
      resolvedPaths: [optOutDir],
      exclude: [],
      debounceMs: 500,
      memoryBank: memoryBank!,
      // Required props of the resolved WatchSourceConfig type — the scenario
      // opts out of auto-populate, so chunking never runs; keep schema defaults.
      sourceType: SOURCE_TYPES.VAULT,
      contentFilter: DEFAULT_CONTENT_FILTER_OPTIONS,
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
