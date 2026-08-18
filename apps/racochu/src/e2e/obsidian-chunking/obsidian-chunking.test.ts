import { FileProcessingQueue } from '@/infrastructure/services/file-processing-queue.service';
import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as path from 'path';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { createTestApplication } from '../main.test-application';

const PROCESSING_WAIT_MS = 20000; // debounce(1000ms) + chunking + MCP ingestion + Mnemosyne indexing

describe('[E2E] Obsidian Chunking — obsidian note → chunk → ingest → recall', () => {
  let app: INestApplication | null = null;
  let bensyneClient: BensyneClient | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let obsidianWatchDir: string | undefined;

  beforeAll(async () => {
    // Read obsidian watch dir from env var set by global-setup.ts
    obsidianWatchDir = process.env.E2E_OBSIDIAN_WATCH_DIR;
    if (!obsidianWatchDir) {
      throw new Error('E2E_OBSIDIAN_WATCH_DIR not set — obsidian watch source missing from E2E config');
    }
    console.log(`[E2E-Obsidian] Using obsidian watch directory: ${obsidianWatchDir}`);

    // Create test application — this triggers bootstrap:
    // FileWatcherService.start() → chokidar watches obsidianWatchDir
    // BensyneClient.initialize() → establishes MCP session
    app = await createTestApplication();
    await app.init();

    bensyneClient = app.get(BensyneClient);
    processingQueue = app.get(FileProcessingQueue);

    // Give FileWatcherService time to fully register watchers
    await new Promise(resolve => setTimeout(resolve, 1000));
    console.log(`[E2E-Obsidian] Server bootstrapped, FileWatcher active`);
  }, 90000);

  afterAll(async () => {
    // Graceful close with 30s timeout; force exit if it hangs
    if (app) {
      const closePromise = app.close();
      const timeoutPromise = new Promise(resolve => setTimeout(resolve, 30000));
      await Promise.race([closePromise, timeoutPromise]);
    }
  });

  it('should detect obsidian note, chunk with the obsidian chunker, ingest, and verify via recall', async () => {
    const uniqueId = Date.now();
    const marker = `OBSIDIAN-E2E-${uniqueId}`;

    const content = `---
aliases:
  - Test Obsidian Note ${uniqueId}
tags:
  - test
  - e2e
base: "[[Test Base]]"
---
This is a test Obsidian note for E2E verification. Unique marker: ${marker}.

It contains [[Wikilink A]] and [[Wikilink B|display alias]] references.

## Section Two

More content with another [[Wikilink C]] reference and the marker ${marker} repeated.`;

    const fileName = `e2e-obsidian-test-${uniqueId}.md`;
    const filePath = path.join(obsidianWatchDir!, fileName);

    // Drop obsidian fixture file into watched folder → FileWatcher detects →
    // ObsidianChunkingStrategy → Mnemosyne
    await fs.writeFile(filePath, content, 'utf-8');
    console.log(`[E2E-Obsidian] Dropped obsidian note: ${filePath}`);

    // Wait for debounce + chunking + MCP ingestion + Mnemosyne indexing
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Verify recall in tmp-obsidian bank — use the unique marker as query
    const recallResult = await bensyneClient!.recall(marker, 5, 1000, 'tmp-obsidian');
    if (!recallResult.isOk()) {
      console.log(`[E2E-Obsidian] Recall FAILED:`, recallResult.getFormattedErrors());
    }
    expect(recallResult.isOk()).toBe(true);
    const results = recallResult.getValue();
    console.log(`[E2E-Obsidian] Recall returned ${results.length} results`);
    if (results.length > 0) {
      console.log(`[E2E-Obsidian] First result: ${JSON.stringify(results[0]).slice(0, 200)}`);
    }
    expect(results.length).toBeGreaterThan(0);

    // Cleanup — delete the test file
    await fs.unlink(filePath);
    console.log(`[E2E-Obsidian] Cleaned up test file: ${filePath}`);
  }, 120000);
});
