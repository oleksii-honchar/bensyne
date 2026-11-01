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

describe('[E2E] File Update Flow — create → ingest → track → update → forget old → ingest new → track new', () => {
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
    console.log(`[E2E-FileUpdate] Using watch directory: ${watchDir}`);

    app = await createTestApplication();
    await app.init();

    bensyneClient = app.get(BensyneClient);
    trackerRepo = app.get(FileMemoryTrackerRepository);

    processingQueue = app.get(FileProcessingQueue);

    // Give FileWatcherService time to fully register watchers
    await new Promise(resolve => setTimeout(resolve, 1000));
    console.log(`[E2E-FileUpdate] Server bootstrapped, FileWatcher active`);
  }, 90000);

  afterAll(async () => {
    if (app) {
      const closePromise = app.close();
      let timeoutId: ReturnType<typeof setTimeout> | undefined;
      const timeoutPromise = new Promise(resolve => {
        timeoutId = setTimeout(resolve, 30000);
      });
      await Promise.race([closePromise, timeoutPromise]);
      // Clear the fallback timer — otherwise Jest sees a pending open handle
      if (timeoutId) clearTimeout(timeoutId);
    }
  });

  it('should create file, ingest chunks, track mapping, update file, forget old memories, ingest new, and track with new IDs', async () => {
    // Step 1: Create a unique test file in the watch directory with marker A
    const uniqueId = Date.now();
    const fileName = `fileupdate-test-${uniqueId}.md`;
    const filePath = path.join(watchDir!, fileName);

    const markerA = `UPDATEFLOW-${uniqueId}`;
    const contentA = `# File Update Test ${uniqueId}\n\nThis is a unique test file for update flow verification. Test marker: ${markerA}.\n\n## Details\n\nThis file will be updated to verify the forget-and-reingest flow.`;
    await fs.writeFile(filePath, contentA, 'utf-8');
    console.log(`[E2E-FileUpdate] Created test file: ${filePath}`);

    // Step 2: Wait for ingestion (debounce + chunking + MCP + indexing)
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Step 3: Verify memory exists via recall for marker A
    const recallBefore = await bensyneClient!.recall(markerA, 5, 1000, 'e2e-test-ns');
    expect(recallBefore.isOk()).toBe(true);
    const recallBeforeResults = recallBefore.getValue();
    console.log(`[E2E-FileUpdate] Recall before update returned ${recallBeforeResults.length} results`);
    expect(recallBeforeResults.length).toBeGreaterThan(0);
    expect(recallBeforeResults.some(r => r.content.includes(markerA))).toBe(true);

    // Step 4: Verify tracker has mapping for the file
    const trackerBefore = await trackerRepo!.findByFilePath(filePath);
    expect(trackerBefore.isOk()).toBe(true);
    const trackerBeforeValue = trackerBefore.getValue();
    expect(trackerBeforeValue).not.toBeNull();
    expect(trackerBeforeValue!.memoryIds.length).toBeGreaterThan(0);
    console.log(
      `[E2E-FileUpdate] Tracker mapping exists before update: ${trackerBeforeValue!.memoryIds.length} memory IDs`,
    );

    // Step 5: Save old tracker memory IDs
    const oldMemoryIds = new Set(trackerBeforeValue!.memoryIds);
    console.log(`[E2E-FileUpdate] Old memory IDs: ${Array.from(oldMemoryIds).join(', ')}`);

    // Step 6: Update the file with new content containing marker B
    const markerB = `UPDATEFLOW-NEW-${uniqueId}`;
    const contentB = `# File Update Test ${uniqueId} — Updated\n\nThis is the updated content for the test file. Test marker: ${markerB}.\n\n## New Details\n\nThe old content has been replaced. Marker A should no longer be found.`;
    await fs.writeFile(filePath, contentB, 'utf-8');
    console.log(`[E2E-FileUpdate] Updated test file with marker B`);

    // Step 7: Wait for change processing (debounce + forget + chunking + MCP + indexing)
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Step 8: Verify recall finds marker B (new content ingested)
    const recallAfterB = await bensyneClient!.recall(markerB, 5, 1000, 'e2e-test-ns');
    expect(recallAfterB.isOk()).toBe(true);
    const recallAfterBResults = recallAfterB.getValue();
    console.log(
      `[E2E-FileUpdate] Recall after update for marker B returned ${recallAfterBResults.length} results`,
    );
    expect(recallAfterBResults.length).toBeGreaterThan(0);
    expect(recallAfterBResults.some(r => r.content.includes(markerB))).toBe(true);

    // Step 9: Verify recall does NOT find marker A (old content forgotten)
    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    const recallAfterA = await bensyneClient!.recall(markerA, 5, 1000, 'e2e-test-ns');
    expect(recallAfterA.isOk()).toBe(true);
    const recallAfterAResults = recallAfterA.getValue();
    console.log(
      `[E2E-FileUpdate] Recall after update for marker A returned ${recallAfterAResults.length} results`,
    );
    const remainingWithMarkerA = recallAfterAResults.filter(r => r.content.includes(markerA));
    expect(remainingWithMarkerA.length).toBe(0);

    // Step 10: Verify tracker has mapping with new memory IDs (not old ones)
    const trackerAfter = await trackerRepo!.findByFilePath(filePath);
    expect(trackerAfter.isOk()).toBe(true);
    const trackerAfterValue = trackerAfter.getValue();
    expect(trackerAfterValue).not.toBeNull();
    expect(trackerAfterValue!.memoryIds.length).toBeGreaterThan(0);
    console.log(
      `[E2E-FileUpdate] Tracker mapping exists after update: ${trackerAfterValue!.memoryIds.length} memory IDs`,
    );

    const newMemoryIds = new Set(trackerAfterValue!.memoryIds);
    console.log(`[E2E-FileUpdate] New memory IDs: ${Array.from(newMemoryIds).join(', ')}`);

    // New memory IDs must be different from old ones (forget + reingest replaced them)
    const hasOldIds = [...oldMemoryIds].some(id => newMemoryIds.has(id));
    expect(hasOldIds).toBe(false);

    // Step 11: Cleanup — delete the test file
    await fs.unlink(filePath);
    console.log(`[E2E-FileUpdate] Cleaned up test file: ${filePath}`);
  }, 120000);

  // Task 9 (spec §8 "file-watcher-flow: touch-without-change fires no re-ingest",
  // C3 hash gate on the CHANGE path). The findings' ×135/×14 classes were
  // mtime-conflict touches from sync tools — bytes unchanged.
  //
  // Observation points (all external): FileTracker row (id/fileHash/skipReason/
  // updatedAt), FileMemoryTracker count + memory ID set, bank chunk count.
  // A gated file performs ZERO writes anywhere, so every field must be
  // bit-identical after the touch — updatedAt included.
  // Limitation (recorded in the T9 report): chunk-classifier/embedding call
  // counts are not instrumented in-process in e2e; the zero-delta observation
  // chain above is the strongest available proxy for "zero chunk work".
  //
  // Phase 3 is the anti-vacuity control: a REAL content change on the very
  // same watched file must still forget+re-ingest — proving the zero-deltas in
  // Phase 2 came from the gate, not from a dead watcher.
  it('touch without content change causes no re-ingest (watch → hash gate), while a real change on the same file still re-ingests', async () => {
    const prisma = app!.get(PrismaService);

    // ── Phase A: fresh file is ingested by the watcher (baseline) ──────
    const uniqueId = Date.now();
    const markerA = `NOTOUCH-A-${uniqueId}`;
    const filePath = path.join(watchDir!, `notouch-test-${uniqueId}.md`);
    const contentA = `# No-Touch Test ${uniqueId}\n\nThis file exists to prove a same-content re-save (mtime touch) is hash-gated end-to-end. Test marker: ${markerA}.\n\n## Details\n\nAfter ingestion the file is re-saved byte-identical; nothing may change in the bank or tracker.`;
    await fs.writeFile(filePath, contentA, 'utf-8');
    console.log(`[E2E-FileUpdate-NoTouch] Created test file: ${filePath}`);

    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();

    const rowBefore = await prisma.fileTracker.findUnique({ where: { filePath } });
    expect(rowBefore).not.toBeNull();
    const expectedHashA = crypto.createHash('sha256').update(contentA).digest('hex');
    expect(rowBefore!.fileHash).toBe(expectedHashA);
    expect(rowBefore!.skipReason).toBeNull();

    const trackerBefore = await trackerRepo!.findByFilePath(filePath);
    expect(trackerBefore.isOk()).toBe(true);
    const memoryIdsBefore = trackerBefore.getValue()!.memoryIds;
    expect(memoryIdsBefore.length).toBeGreaterThan(0);
    const memoryCountBefore = await prisma.fileMemoryTracker.count({
      where: { fileTrackerId: rowBefore!.id },
    });
    expect(memoryCountBefore).toBe(memoryIdsBefore.length);

    const chunksBeforeResult = await bensyneClient!.getFileChunks(filePath, 'e2e-test-ns');
    expect(chunksBeforeResult.isOk()).toBe(true);
    const chunksBefore = chunksBeforeResult.getValue().chunks.length;
    expect(chunksBefore).toBeGreaterThan(0);
    console.log(
      `[E2E-FileUpdate-NoTouch] Baseline: memories=${memoryCountBefore}, bankChunks=${chunksBefore}, fileHash=${rowBefore!.fileHash}`,
    );

    // ── Phase B: same-content re-save (= what an mtime touch looks like to
    // the pipeline: chokidar 'change' event, bytes identical) ───────────
    await fs.writeFile(filePath, contentA, 'utf-8');
    console.log(`[E2E-FileUpdate-NoTouch] Touched file with identical bytes`);

    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();

    // Zero new memory rows, zero forgotten rows.
    const trackerAfter = await trackerRepo!.findByFilePath(filePath);
    expect(trackerAfter.isOk()).toBe(true);
    const memoryIdsAfter = trackerAfter.getValue()!.memoryIds;
    expect([...memoryIdsAfter].sort()).toEqual([...memoryIdsBefore].sort());
    const memoryCountAfter = await prisma.fileMemoryTracker.count({
      where: { fileTrackerId: rowBefore!.id },
    });
    expect(memoryCountAfter).toBe(memoryCountBefore);

    // FileTracker untouched: same row (no delete/recreate), hash unchanged,
    // skipReason still null, and updatedAt unmoved — the gate issues NO write.
    const rowAfterTouch = await prisma.fileTracker.findUnique({ where: { filePath } });
    expect(rowAfterTouch).not.toBeNull();
    expect(rowAfterTouch!.id).toEqual(rowBefore!.id);
    expect(rowAfterTouch!.fileHash).toBe(rowBefore!.fileHash);
    expect(rowAfterTouch!.skipReason).toBeNull();
    expect(rowAfterTouch!.updatedAt.getTime()).toBe(rowBefore!.updatedAt.getTime());

    // No chunk operations reached the bank for the touched file.
    const chunksAfterResult = await bensyneClient!.getFileChunks(filePath, 'e2e-test-ns');
    expect(chunksAfterResult.isOk()).toBe(true);
    expect(chunksAfterResult.getValue().chunks.length).toBe(chunksBefore);
    console.log(
      `[E2E-FileUpdate-NoTouch] After touch: memories=${memoryCountAfter} (unchanged), bankChunks=${chunksAfterResult.getValue().chunks.length} (unchanged), updatedAt unchanged=${rowAfterTouch!.updatedAt.getTime() === rowBefore!.updatedAt.getTime()}`,
    );

    // ── Phase C: control — a REAL change on this same watched file must
    // still run the full DEC-0036 forget+re-ingest flow. ────────────────
    const markerB = `NOTOUCH-B-${uniqueId}`;
    const contentB = `# No-Touch Test ${uniqueId} — Really Changed\n\nThis edit changes the bytes, so the gate must NOT fire and the full change flow must run. Test marker: ${markerB}.`;
    await fs.writeFile(filePath, contentB, 'utf-8');
    console.log(`[E2E-FileUpdate-NoTouch] Applied real content change (marker B)`);

    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();

    const rowChanged = await prisma.fileTracker.findUnique({ where: { filePath } });
    expect(rowChanged).not.toBeNull();
    expect(rowChanged!.fileHash).toBe(crypto.createHash('sha256').update(contentB).digest('hex'));

    const trackerChanged = await trackerRepo!.findByFilePath(filePath);
    expect(trackerChanged.isOk()).toBe(true);
    const memoryIdsChanged = new Set(trackerChanged.getValue()!.memoryIds);
    expect(memoryIdsChanged.size).toBeGreaterThan(0);
    // Old memories were replaced (forget + re-ingest), i.e. the watcher was
    // live for this file the whole time.
    const stillHasOld = [...memoryIdsBefore].some(id => memoryIdsChanged.has(id));
    expect(stillHasOld).toBe(false);
    console.log(
      `[E2E-FileUpdate-NoTouch] Control: real change re-ingested (memory IDs fully replaced: ${memoryIdsChanged.size} new)`,
    );

    // Cleanup — delete the test file
    await fs.unlink(filePath);
    console.log(`[E2E-FileUpdate-NoTouch] Cleaned up test file: ${filePath}`);
  }, 180000);
});
