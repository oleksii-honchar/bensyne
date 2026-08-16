import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as path from 'path';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { readFixture } from '../e2e-utils';
import { createTestApplication } from '../main.test-application';

const PROCESSING_WAIT_MS = 20000; // debounce(500ms) + chunking + MCP ingestion + Mnemosyne indexing

import { FileProcessingQueue } from '@/infrastructure/services/file-processing-queue.service';

describe('[E2E] FileWatcher Flow — file creation → watch → chunk → ingest → recall', () => {
  let app: INestApplication | null = null;
  let bensyneClient: BensyneClient | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let watchDir: string | undefined;

  beforeAll(async () => {
    // Read watch dir from env var set by global-setup.ts (shared across Jest workers)
    watchDir = process.env.E2E_WATCH_DIR;
    if (!watchDir) {
      throw new Error('Watch directory not found in config file');
    }
    console.log(`[E2E-FileWatcher] Using watch directory from config: ${watchDir}`);

    // Create test application — this triggers bootstrap:
    // FileWatcherService.start() → chokidar watches watchDir
    // BensyneClient.initialize() → establishes MCP session
    app = await createTestApplication();
    await app.init();

    bensyneClient = app.get(BensyneClient);
    processingQueue = app.get(FileProcessingQueue);

    // Give FileWatcherService time to fully register watchers
    await new Promise(resolve => setTimeout(resolve, 1000));
    console.log(`[E2E-FileWatcher] Server bootstrapped, FileWatcher active`);
  }, 90000);

  afterAll(async () => {
    // Watch directory is cleaned up by global-teardown.ts

    // Graceful close with 30s timeout; force exit if it hangs
    if (app) {
      const closePromise = app.close();
      const timeoutPromise = new Promise(resolve => setTimeout(resolve, 30000));
      await Promise.race([closePromise, timeoutPromise]);
    }
  });

  it('should detect markdown file, chunk it, ingest to Mnemosyne, and verify via recall', async () => {
    const content = await readFixture('sample.md');
    const fileName = 'filewatcher-test-markdown.md';
    const filePath = path.join(watchDir!, fileName);

    // Drop fixture file into watched folder → FileWatcher detects → ProcessFileUseCase → Mnemosyne
    await fs.writeFile(filePath, content, 'utf-8');
    console.log(`[E2E-FileWatcher] Dropped markdown fixture: ${filePath}`);

    // Wait for debounce + chunking + MCP ingestion + Mnemosyne indexing
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Verify recall call succeeds (Mnemosyne session shared with BensyneClient)
    // Mnemosyne uses semantic search, so use a broad query that matches sample.md content
    const recallResult = await bensyneClient!.recall('chunking', 5, 1000, 'e2e-test-ns');
    if (!recallResult.isOk()) {
      console.log(`[E2E-FileWatcher] Recall("chunking") FAILED:`, recallResult.getFormattedErrors());
    }
    expect(recallResult.isOk()).toBe(true);
    const results = recallResult.getValue();
    console.log(`[E2E-FileWatcher] Recall("chunking") returned ${results.length} results`);
    if (results.length > 0) {
      console.log(`[E2E-FileWatcher] First result: ${JSON.stringify(results[0]).slice(0, 200)}`);
    }
    // Mnemosyne may return related results via semantic search
    expect(results.length).toBeGreaterThan(0);
  }, 120000);

  it('should detect TypeScript file, chunk it, ingest to Mnemosyne, and verify via recall', async () => {
    const content = await readFixture('sample.ts');
    const fileName = 'filewatcher-test-typescript.ts';
    const filePath = path.join(watchDir!, fileName);

    // Drop fixture file into watched folder
    await fs.writeFile(filePath, content, 'utf-8');
    console.log(`[E2E-FileWatcher] Dropped TypeScript fixture: ${filePath}`);

    // Wait for debounce + chunking + MCP ingestion + Mnemosyne indexing
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Verify recall call succeeds
    const recallResult = await bensyneClient!.recall('service chunk', 5, 1000, 'e2e-test-ns');
    expect(recallResult.isOk()).toBe(true);
    const results = recallResult.getValue();
    expect(results.length).toBeGreaterThan(0);
  }, 120000);

  it('should detect JSON file, chunk it, ingest to Mnemosyne, and verify via recall', async () => {
    const content = await readFixture('sample.json');
    const fileName = 'filewatcher-test-config.json';
    const filePath = path.join(watchDir!, fileName);

    // Drop fixture file into watched folder
    await fs.writeFile(filePath, content, 'utf-8');
    console.log(`[E2E-FileWatcher] Dropped JSON fixture: ${filePath}`);

    // Wait for debounce + chunking + MCP ingestion + Mnemosyne indexing
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));

    // Wait for processing queue to drain before recall
    await processingQueue!.waitForEmpty();

    // Verify recall call succeeds
    const recallResult = await bensyneClient!.recall('config', 5, 1000, 'e2e-test-ns');
    expect(recallResult.isOk()).toBe(true);
    const results = recallResult.getValue();
    expect(results.length).toBeGreaterThan(0);
  }, 120000);
});
