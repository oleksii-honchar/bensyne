import { PrismaService } from '@/infrastructure/prisma/prisma.service';
import { FileMemoryTrackerRepository } from '@/infrastructure/repositories/file-memory-tracker.repository';
import { BensyneClient } from '@/infrastructure/services/bensyne-client.service';
import { FileProcessingQueue } from '@/infrastructure/services/file-processing-queue.service';
import { INestApplication } from '@nestjs/common';
import * as crypto from 'crypto';
import * as fs from 'fs/promises';
import * as path from 'path';
import { createTestApplication } from '../main.test-application';

const PROCESSING_WAIT_MS = 20000; // debounce(500ms) + chunking + MCP ingestion + Mnemosyne indexing

describe('[E2E] File Hash Dedup — Same File From Second Device Is Deduplicated', () => {
  let app: INestApplication | null = null;
  let bensyneClient: BensyneClient | null = null;
  let trackerRepo: FileMemoryTrackerRepository | null = null;
  let prisma: PrismaService | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let watchDir: string | undefined;

  beforeAll(async () => {
    watchDir = process.env.E2E_WATCH_DIR;
    if (!watchDir) {
      throw new Error('E2E_WATCH_DIR not set');
    }
    console.log(`[E2E-Dedup] Using watch directory: ${watchDir}`);

    app = await createTestApplication();
    await app.init();

    bensyneClient = app.get(BensyneClient);
    trackerRepo = app.get(FileMemoryTrackerRepository);
    prisma = app.get(PrismaService);
    processingQueue = app.get(FileProcessingQueue);

    // Give FileWatcherService time to fully register watchers
    await new Promise(resolve => setTimeout(resolve, 1000));
    console.log(`[E2E-Dedup] Server bootstrapped, FileWatcher active`);
  }, 90000);

  afterAll(async () => {
    if (app) {
      const closePromise = app.close();
      let timeoutId: ReturnType<typeof setTimeout> | undefined;
      const timeoutPromise = new Promise(resolve => {
        timeoutId = setTimeout(resolve, 30000);
      });
      await Promise.race([closePromise, timeoutPromise]);
      if (timeoutId) clearTimeout(timeoutId);
    }
  });

  it('should ingest the same file content from two different paths and deduplicate, keeping only one memory', async () => {
    const uniqueId = Date.now();
    const marker = `DEDUP-${uniqueId}`;

    // Shared content — both files have identical text, producing the same SHA-256 hash
    const sharedContent = `# Dedup Test ${uniqueId}\n\nThis is a unique test file for cross-device deduplication verification.\nTest marker: ${marker}.\n\n## Details\n\nThis content is ingested from two different file paths with the same hash.`;
    const expectedHash = crypto.createHash('sha256').update(sharedContent).digest('hex');
    console.log(`[E2E-Dedup] Expected fileHash: ${expectedHash}`);

    // ── Phase 1: Ingest first file ──────────────────────────────────────

    const fileName1 = `dedup-device1-${uniqueId}.md`;
    const filePath1 = path.join(watchDir!, fileName1);
    await fs.writeFile(filePath1, sharedContent, 'utf-8');
    console.log(`[E2E-Dedup] Created first file: ${filePath1}`);

    // Wait for ingestion
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Verify memory is stored via recall
    const recallAfterFirst = await bensyneClient!.recall(marker, 5, 1000, 'e2e-test-ns');
    expect(recallAfterFirst.isOk()).toBe(true);
    const resultsAfterFirst = recallAfterFirst.getValue();
    console.log(`[E2E-Dedup] Recall after first file: ${resultsAfterFirst.length} results`);
    expect(resultsAfterFirst.length).toBeGreaterThan(0);
    expect(resultsAfterFirst.some(r => r.content.includes(marker))).toBe(true);

    // Verify FileTracker has a mapping for the first file
    const tracker1 = await trackerRepo!.findByFilePath(filePath1);
    expect(tracker1.isOk()).toBe(true);
    expect(tracker1.getValue()).not.toBeNull();
    expect(tracker1.getValue()!.memoryIds.length).toBeGreaterThan(0);
    console.log(`[E2E-Dedup] First file tracker: ${tracker1.getValue()!.memoryIds.length} memory IDs`);

    // Verify fileHash on first file tracker
    const fileTracker1 = await prisma!.fileTracker.findUnique({
      where: { filePath: filePath1 },
    });
    expect(fileTracker1).not.toBeNull();
    expect(fileTracker1!.fileHash).toBe(expectedHash);
    console.log(`[E2E-Dedup] First file fileHash: ${fileTracker1!.fileHash}`);

    // Save the count of memories after first ingestion for comparison
    const memoryCountAfterFirst = resultsAfterFirst.length;

    // ── Phase 2: Ingest second file (same content, different path) ─────

    const fileName2 = `dedup-device2-${uniqueId}.md`;
    const filePath2 = path.join(watchDir!, fileName2);
    await fs.writeFile(filePath2, sharedContent, 'utf-8');
    console.log(`[E2E-Dedup] Created second file (same content): ${filePath2}`);

    // Wait for ingestion
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Verify recall still returns the same memory (no duplicates)
    const recallAfterSecond = await bensyneClient!.recall(marker, 5, 1000, 'e2e-test-ns');
    expect(recallAfterSecond.isOk()).toBe(true);
    const resultsAfterSecond = recallAfterSecond.getValue();
    console.log(`[E2E-Dedup] Recall after second file: ${resultsAfterSecond.length} results`);
    expect(resultsAfterSecond.length).toBeGreaterThan(0);
    expect(resultsAfterSecond.some(r => r.content.includes(marker))).toBe(true);

    // CRITICAL: Memory count should be the same — dedup prevented a second memory
    expect(resultsAfterSecond.length).toBe(memoryCountAfterFirst);
    console.log(
      `[E2E-Dedup] Memory count unchanged: ${memoryCountAfterFirst} → ${resultsAfterSecond.length} (dedup successful)`,
    );

    // Verify FileTracker has a separate mapping for the second file path
    const tracker2 = await trackerRepo!.findByFilePath(filePath2);
    expect(tracker2.isOk()).toBe(true);
    expect(tracker2.getValue()).not.toBeNull();
    console.log(`[E2E-Dedup] Second file tracker: ${tracker2.getValue()!.memoryIds.length} memory IDs`);

    // Verify fileHash on second file tracker matches the same hash
    const fileTracker2 = await prisma!.fileTracker.findUnique({
      where: { filePath: filePath2 },
    });
    expect(fileTracker2).not.toBeNull();
    expect(fileTracker2!.fileHash).toBe(expectedHash);
    console.log(`[E2E-Dedup] Second file fileHash: ${fileTracker2!.fileHash}`);

    // Verify both trackers share the same fileHash (same content)
    expect(fileTracker1!.fileHash).toBe(fileTracker2!.fileHash);

    // ── Phase 3: Cleanup ────────────────────────────────────────────────

    await fs.unlink(filePath1);
    await fs.unlink(filePath2);
    console.log(`[E2E-Dedup] Cleaned up both test files`);
  }, 120000);
});
