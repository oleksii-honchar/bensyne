import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as path from 'path';
import { FileMemoryTrackerRepository } from '../../infrastructure/repositories/file-memory-tracker.repository';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileProcessingQueue } from '@/infrastructure/services/file-processing-queue.service';
// readFixture available if needed for reference
import { createTestApplication } from '../main.test-application';

const PROCESSING_WAIT_MS = 20000; // debounce(500ms) + chunking + MCP ingestion + Mnemosyne indexing

describe('[E2E] File Deletion Cleanup — create → ingest → track → delete → forget → untrack', () => {
  let app: INestApplication | null = null;
  let bensyneClient: BensyneClient | null = null;
  let trackerRepo: FileMemoryTrackerRepository | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let watchDir: string | undefined;

  beforeAll(async () => {
    watchDir = process.env.E2E_WATCH_DIR;
    if (!watchDir) {
      throw new Error('E2E_WATCH_DIR not set');
    }
    console.log(`[E2E-FileDeletion] Using watch directory: ${watchDir}`);

    app = await createTestApplication();
    await app.init();

    bensyneClient = app.get(BensyneClient);
    trackerRepo = app.get(FileMemoryTrackerRepository);

    processingQueue = app.get(FileProcessingQueue);

    // Give FileWatcherService time to fully register watchers
    await new Promise(resolve => setTimeout(resolve, 1000));
    console.log(`[E2E-FileDeletion] Server bootstrapped, FileWatcher active`);
  }, 90000);

  afterAll(async () => {
    if (app) {
      const closePromise = app.close();
      const timeoutPromise = new Promise(resolve => setTimeout(resolve, 30000));
      await Promise.race([closePromise, timeoutPromise]);
    }
  });

  it('should create file, ingest chunks, track mapping, delete file, forget memories, and remove mapping', async () => {
    // Step 1: Create a unique test file in the watch directory
    // content fixture available if needed for reference
    const uniqueId = Date.now();
    const fileName = `filedeletion-test-${uniqueId}.md`;
    const filePath = path.join(watchDir!, fileName);

    // Use a unique query phrase embedded in content for reliable recall verification
    const uniqueContent = `# File Deletion Test ${uniqueId}\n\nThis is a unique test file for deletion cleanup verification. Test marker: FILEDELETION-${uniqueId}.\n\n## Details\n\nThis file should be tracked and forgotten when deleted.`;
    await fs.writeFile(filePath, uniqueContent, 'utf-8');
    console.log(`[E2E-FileDeletion] Created test file: ${filePath}`);

    // Step 2: Wait for ingestion (debounce + chunking + MCP + indexing)
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Step 3: Verify memory exists via memory_recall
    const recallResult = await bensyneClient!.recall(`FILEDELETION-${uniqueId}`, 5, 1000, 'e2e-test-ns');
    expect(recallResult.isOk()).toBe(true);
    const recallResults = recallResult.getValue();
    console.log(`[E2E-FileDeletion] Recall returned ${recallResults.length} results`);
    expect(recallResults.length).toBeGreaterThan(0);
    expect(recallResults.some(r => r.includes(`FILEDELETION-${uniqueId}`))).toBe(true);

    // Step 4: Verify tracker.db has file→memory mapping
    const trackerBefore = await trackerRepo!.findByFilePath(filePath);
    expect(trackerBefore.isOk()).toBe(true);
    const trackerBeforeValue = trackerBefore.getValue();
    expect(trackerBeforeValue).not.toBeNull();
    expect(trackerBeforeValue!.memoryIds.length).toBeGreaterThan(0);
    console.log(
      `[E2E-FileDeletion] Tracker mapping exists: ${trackerBeforeValue!.memoryIds.length} memory IDs`,
    );

    // Step 5: Delete the file
    await fs.unlink(filePath);
    console.log(`[E2E-FileDeletion] Deleted test file: ${filePath}`);

    // Step 6: Wait for delete handler (debounce + processing)
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Step 7: Verify memory was forgotten — recall returns no results for this file's unique marker
    const recallAfter = await bensyneClient!.recall(`FILEDELETION-${uniqueId}`, 5, 1000, 'e2e-test-ns');
    expect(recallAfter.isOk()).toBe(true);
    const recallResultsAfter = recallAfter.getValue();
    console.log(`[E2E-FileDeletion] Recall after delete returned ${recallResultsAfter.length} results`);
    // All results containing our unique marker should be gone
    const remainingWithMarker = recallResultsAfter.filter(r => r.includes(`FILEDELETION-${uniqueId}`));
    expect(remainingWithMarker.length).toBe(0);

    // Step 8: Verify tracker.db mapping removed
    const trackerAfter = await trackerRepo!.findByFilePath(filePath);
    expect(trackerAfter.isKo()).toBe(true);
    console.log(`[E2E-FileDeletion] Tracker mapping removed successfully`);
  }, 120000);
});
