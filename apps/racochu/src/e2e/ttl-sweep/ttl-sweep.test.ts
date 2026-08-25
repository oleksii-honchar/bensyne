import { FileProcessingQueue } from '@/infrastructure/services/file-processing-queue.service';
import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import { DatabaseSync } from 'node:sqlite';
import * as path from 'path';
import { TtlReconciliationService } from '../../application/ttl-reconciliation.service';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { PrismaService } from '../../infrastructure/prisma/prisma.service';
import { FileMemoryTrackerRepository } from '../../infrastructure/repositories/file-memory-tracker.repository';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { createTestApplication } from '../main.test-application';

const PROCESSING_WAIT_MS = 20000; // debounce(500ms) + chunking + MCP ingestion + Mnemosyne indexing
const MS_PER_DAY = 86_400_000;
const TTL_DAYS = 365;
const BACKDATE_DAYS = 400; // 400 > 365 → definitely expired

const SOURCE_ID = 'e2e-test-source';
const OBSIDIAN_SOURCE_ID = 'e2e-obsidian-source';
const MEMORY_BANK = 'e2e-test-ns';

describe('[E2E] TTL Sweep — ingest → dry-run → real sweep (tombstone, idempotency, opt-in scope)', () => {
  let app: INestApplication | null = null;
  let bensyneClient: BensyneClient | null = null;
  let trackerRepo: FileMemoryTrackerRepository | null = null;
  let prisma: PrismaService | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let ttlService: TtlReconciliationService | null = null;
  let configurationService: ConfigurationService | null = null;
  let watchDir: string | undefined;
  let e2eDataDir: string | undefined;

  // Shared across the 3 sequential tests (maxWorkers: 1).
  let uniqueId: number;
  let marker: string;
  let filePath: string;

  /**
   * Read-only handle on the bensyne bank's file metadata DB
   * ({E2E_DATA_DIR}/banks/{memory_bank}/file_metadata.db — router.py banks layout).
   */
  function openFileMetadataDb(): DatabaseSync {
    const dbPath = path.join(e2eDataDir!, 'banks', MEMORY_BANK, 'file_metadata.db');
    console.log(`[E2E-TtlSweep] Opening bensyne file metadata DB: ${dbPath}`);
    return new DatabaseSync(dbPath, { readOnly: true });
  }

  function findFileRow(db: DatabaseSync, targetPath: string): { id: string; status: string } | undefined {
    const row = db.prepare('SELECT id, status FROM files WHERE path = ?').get(targetPath) as
      { id: string; status: string } | undefined;
    return row;
  }

  function countChunksForFile(db: DatabaseSync, fileId: string): number {
    const row = db.prepare('SELECT COUNT(*) AS c FROM file_chunks WHERE file_id = ?').get(fileId) as {
      c: number;
    };
    return Number(row.c);
  }

  beforeAll(async () => {
    watchDir = process.env.E2E_WATCH_DIR;
    e2eDataDir = process.env.E2E_DATA_DIR;
    if (!watchDir) {
      throw new Error('E2E_WATCH_DIR not set');
    }
    if (!e2eDataDir) {
      throw new Error('E2E_DATA_DIR not set');
    }
    console.log(`[E2E-TtlSweep] Using watch directory: ${watchDir}`);
    console.log(`[E2E-TtlSweep] Using mnemosyne data directory: ${e2eDataDir}`);

    app = await createTestApplication();
    await app.init();

    bensyneClient = app.get(BensyneClient);
    trackerRepo = app.get(FileMemoryTrackerRepository);
    prisma = app.get(PrismaService);
    processingQueue = app.get(FileProcessingQueue);
    ttlService = app.get(TtlReconciliationService);
    configurationService = app.get(ConfigurationService);

    // Deterministic sweep: forget any trackers left by earlier e2e runs (or
    // earlier suites in this run) for the TTL source, so `expired`/`forgotten`
    // counts are exactly what this suite creates.
    await prisma!.fileTracker.deleteMany({ where: { sourceId: SOURCE_ID } });

    // Give FileWatcherService time to fully register watchers
    await new Promise(resolve => setTimeout(resolve, 1000));
    console.log(`[E2E-TtlSweep] Server bootstrapped, FileWatcher active`);
  }, 90000);

  afterAll(async () => {
    if (app) {
      const closePromise = app.close();
      const timeoutPromise = new Promise(resolve => setTimeout(resolve, 30000));
      await Promise.race([closePromise, timeoutPromise]);
    }
  });

  it('1. ingest baseline — file tracked, recallable, bensyne files row indexed', async () => {
    // Config-side opt-in scope: only e2e-test-source carries ttlDays.
    const sources = configurationService!.getWatchSources();
    const testSource = sources.find(s => s.id === SOURCE_ID);
    const obsidianSource = sources.find(s => s.id === OBSIDIAN_SOURCE_ID);
    expect(testSource).toBeDefined();
    expect(testSource!.ttlDays).toBe(TTL_DAYS);
    expect(obsidianSource).toBeDefined();
    expect(obsidianSource!.ttlDays).toBeUndefined();

    uniqueId = Date.now();
    marker = `TTL-SWEEP-${uniqueId}`;
    const fileName = `ttl-test-${uniqueId}.md`;
    filePath = path.join(watchDir!, fileName);

    const content = `# TTL Sweep Test ${uniqueId}\n\nThis file is used to verify source-level TTL forgetting. Test marker: ${marker}.\n\n## Details\n\nThe tracker will be backdated past the 365-day TTL so the sweep forgets it while the source file stays on disk.`;
    await fs.writeFile(filePath, content, 'utf-8');
    console.log(`[E2E-TtlSweep] Created test file: ${filePath}`);

    // Wait for ingestion (debounce + chunking + MCP + indexing)
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();

    // Memory monitor: recall finds the marker.
    const recallResult = await bensyneClient!.recall(marker, 5, 1000, MEMORY_BANK);
    expect(recallResult.isOk()).toBe(true);
    const recallResults = recallResult.getValue();
    console.log(`[E2E-TtlSweep] Recall returned ${recallResults.length} results`);
    expect(recallResults.length).toBeGreaterThan(0);
    expect(recallResults.some(r => r.content.includes(marker))).toBe(true);

    // Tracker monitor: racochu tracker exists with memory mappings.
    const tracker = await trackerRepo!.findByFilePath(filePath);
    expect(tracker.isOk()).toBe(true);
    expect(tracker.getValue()).not.toBeNull();
    expect(tracker.getValue()!.memoryIds.length).toBeGreaterThan(0);
    console.log(`[E2E-TtlSweep] Tracker memory IDs: ${tracker.getValue()!.memoryIds.length}`);

    // File monitor: bensyne files row is indexed (not tombstoned).
    const db = openFileMetadataDb();
    try {
      const fileRow = findFileRow(db, filePath);
      expect(fileRow).toBeDefined();
      expect(fileRow!.status).toBe('indexed');
      console.log(`[E2E-TtlSweep] Bensyne files row status: ${fileRow!.status}`);
    } finally {
      db.close();
    }
  }, 120000);

  it('2. dry-run sweep — wouldForget 1, forgotten 0, nothing deleted', async () => {
    // Backdate the tracker past the 365-day TTL (400 days).
    const backdated = new Date(Date.now() - BACKDATE_DAYS * MS_PER_DAY);
    const update = await prisma!.fileTracker.updateMany({
      where: { filePath },
      data: { createdAt: backdated },
    });
    expect(update.count).toBe(1);
    console.log(`[E2E-TtlSweep] Backdated tracker: ${update.count} row(s)`);

    const summary = await ttlService!.run(true);
    console.log(`[E2E-TtlSweep] Dry-run summary: ${JSON.stringify(summary)}`);
    // Only the ttlDays source is swept — e2e-obsidian-source is out of scope.
    expect(summary.sourcesChecked).toBe(1);
    expect(summary.expired).toBe(1);
    expect(summary.wouldForget).toBe(1);
    expect(summary.forgotten).toBe(0);
    expect(summary.failed).toBe(0);

    // Dry-run deletes nothing: recall still returns the marker.
    const recallResult = await bensyneClient!.recall(marker, 5, 1000, MEMORY_BANK);
    expect(recallResult.isOk()).toBe(true);
    expect(recallResult.getValue().some(r => r.content.includes(marker))).toBe(true);
  }, 120000);

  it('3. real sweep — forgotten 1, tombstone in bensyne, tracker gone, file on disk, idempotent', async () => {
    const summary = await ttlService!.run();
    console.log(`[E2E-TtlSweep] Real sweep summary: ${JSON.stringify(summary)}`);
    expect(summary.sourcesChecked).toBe(1);
    expect(summary.expired).toBe(1);
    expect(summary.forgotten).toBe(1);
    expect(summary.failed).toBe(0);

    // Memory monitor: the marker is gone from recall.
    const recallAfter = await bensyneClient!.recall(marker, 5, 1000, MEMORY_BANK);
    expect(recallAfter.isOk()).toBe(true);
    const remainingWithMarker = recallAfter.getValue().filter(r => r.content.includes(marker));
    expect(remainingWithMarker.length).toBe(0);
    console.log(`[E2E-TtlSweep] Recall after sweep: no results contain the marker`);

    // Tracker monitor: racochu tracker is gone.
    const trackerAfter = await trackerRepo!.findByFilePath(filePath);
    expect(trackerAfter.isKo()).toBe(true);

    // File monitor: ADR-6 tombstone — files row status 'deleted', chunks gone.
    const db = openFileMetadataDb();
    try {
      const fileRow = findFileRow(db, filePath);
      expect(fileRow).toBeDefined();
      expect(fileRow!.status).toBe('deleted');
      console.log(`[E2E-TtlSweep] Bensyne files row status: ${fileRow!.status}`);
      const chunkCount = countChunksForFile(db, fileRow!.id);
      console.log(`[E2E-TtlSweep] Bensyne file_chunks rows remaining: ${chunkCount}`);
      expect(chunkCount).toBe(0);
    } finally {
      db.close();
    }

    // Disk semantics: the source file still exists (TTL forgets on age, not removal).
    let fileExists = true;
    try {
      await fs.access(filePath);
    } catch {
      fileExists = false;
    }
    expect(fileExists).toBe(true);

    // Idempotency: a second sweep has nothing left to forget.
    const secondSummary = await ttlService!.run();
    console.log(`[E2E-TtlSweep] Second sweep summary: ${JSON.stringify(secondSummary)}`);
    expect(secondSummary.expired).toBe(0);
    expect(secondSummary.forgotten).toBe(0);
    expect(secondSummary.failed).toBe(0);
  }, 120000);
});
