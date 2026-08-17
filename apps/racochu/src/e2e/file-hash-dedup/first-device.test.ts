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

describe('[E2E] File Hash Dedup — First Device Ingestion', () => {
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
    console.log(`[E2E-FileHashDedup] Using watch directory: ${watchDir}`);

    app = await createTestApplication();
    await app.init();

    bensyneClient = app.get(BensyneClient);
    trackerRepo = app.get(FileMemoryTrackerRepository);
    prisma = app.get(PrismaService);
    processingQueue = app.get(FileProcessingQueue);

    // Give FileWatcherService time to fully register watchers
    await new Promise(resolve => setTimeout(resolve, 1000));
    console.log(`[E2E-FileHashDedup] Server bootstrapped, FileWatcher active`);
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

  it('should ingest a file from first device, store memory, and record fileHash + hardwareId', async () => {
    // Step 1: Create a fixture file with known unique content
    const uniqueId = Date.now();
    const fileName = `first-device-${uniqueId}.md`;
    const filePath = path.join(watchDir!, fileName);

    const marker = `FIRSTDEVICE-${uniqueId}`;
    const content = `# First Device Test ${uniqueId}\n\nThis is a unique test file for first device ingestion verification.\nTest marker: ${marker}.\n\n## Details\n\nThis file is ingested from the first device with known content for hash verification.`;
    await fs.writeFile(filePath, content, 'utf-8');
    console.log(`[E2E-FileHashDedup] Created test file: ${filePath}`);

    // Pre-compute expected SHA-256 hash for verification
    const expectedHash = crypto.createHash('sha256').update(content).digest('hex');
    console.log(`[E2E-FileHashDedup] Expected fileHash: ${expectedHash}`);

    // Step 2: Wait for ingestion (debounce + chunking + MCP + indexing)
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Step 3: Verify memory is stored in Mnemosyne via recall
    const recallResult = await bensyneClient!.recall(marker, 5, 1000, 'e2e-test-ns');
    expect(recallResult.isOk()).toBe(true);
    const recallResults = recallResult.getValue();
    console.log(`[E2E-FileHashDedup] Recall returned ${recallResults.length} results`);
    expect(recallResults.length).toBeGreaterThan(0);
    expect(recallResults.some(r => r.content.includes(marker))).toBe(true);

    // Step 4: Verify FileTracker has a mapping for the file
    const trackerResult = await trackerRepo!.findByFilePath(filePath);
    expect(trackerResult.isOk()).toBe(true);
    const tracker = trackerResult.getValue();
    expect(tracker).not.toBeNull();
    expect(tracker!.memoryIds.length).toBeGreaterThan(0);
    console.log(`[E2E-FileHashDedup] Tracker mapping: ${tracker!.memoryIds.length} memory IDs`);

    // Step 5: Verify FileTracker has fileHash and hardwareId via direct Prisma query
    const fileTracker = await prisma!.fileTracker.findUnique({
      where: { filePath },
    });
    expect(fileTracker).not.toBeNull();
    expect(fileTracker!.fileHash).not.toBeNull();
    expect(fileTracker!.fileHash).toBe(expectedHash);
    expect(fileTracker!.hardwareId).not.toBeNull();
    expect(typeof fileTracker!.hardwareId).toBe('string');
    expect(fileTracker!.hardwareId!.length).toBeGreaterThan(0);
    console.log(
      `[E2E-FileHashDedup] FileTracker fileHash: ${fileTracker!.fileHash}, hardwareId: ${fileTracker!.hardwareId}`,
    );

    // Step 6: Cleanup — delete the test file
    await fs.unlink(filePath);
    console.log(`[E2E-FileHashDedup] Cleaned up test file: ${filePath}`);
  }, 120000);
});
