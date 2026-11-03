/**
 * [E2E] Never-ingestable quarantine (Task 9 — spec §8 "add never-ingestable.spec",
 * C1/C2/C3 skip-rows + C8 BatchRunSummary-as-data).
 *
 * HERMETIC source by construction: the corpus lives in a temp dir OUTSIDE the
 * e2e config watch sources, and the explicit WatchSourceConfig is passed
 * directly to ForceReprocessService (same in-test source pattern the
 * auto-population suite's Scenario D uses). No chokidar watcher ever sees the
 * dir, nothing else shares the corpus, so every expected BatchRunSummary
 * counter below is EXACT rather than a lower bound.
 *
 * Proof chain:
 * RUN 1 — first reconciliation pass (`autoPopulateSources([testSource])`, the
 * startup path per spec C7):
 *   - 0-byte and whitespace-only files reach a terminal skip: FileTracker row
 *     with skipReason='empty-content' (spec C3.4 pre-empts the zod too_small
 *     class), zero FileMemoryTracker rows, zero bank chunk rows.
 *   - A 100k-character single-line file trips the DEFAULT content classifier
 *     (deterministic pure-function heuristics, no LLM) and records
 *     skipReason='content-filtered' — same quarantine (DEC-A2).
 *   - An ordinary note is fully ingested (memories tracked + bank chunks).
 * RUN 2 — same call again (what a second manual watch-start does),
 * expectations re-baselined per DEC-A7 (spec §8 / §3 mode table):
 *   - The resume/auto-populate queue is NEW-FILES-ONLY: every corpus file now
 *     has a FileTracker row — skip-rows ARE rows ⇒ known — so the queue is
 *     STRUCTURALLY EMPTY before any per-file work. The returned
 *     BatchRunSummary is ALL ZERO (files=0; gated-skips / terminal-skip-skips
 *     / verified-skips / re-ingested 0: with nothing queued these counters
 *     are structurally 0 on this path — the bank-verification counter is
 *     retired with DEC-A7). files=0 is the healthy repeat-run signature.
 *   - ZERO chunk operations for the never-ingestable files: bank chunk counts
 *     stay 0 and their FileTracker rows (hash, skipReason, updatedAt) are
 *     byte-identical — the M2 retry loop is now closed at queue-construction
 *     level (row subtraction), at literally zero per-file cost. Summary
 *     asserted on the BatchRunSummary RETURNED AS DATA (T6/C8), the strongest
 *     e2e surface without log scraping.
 *
 * Deliberate scope limit (stated in the T9 report): the 'zero-chunks' class
 * needs a fixture that deterministically produces zero chunks from nonempty,
 * non-filtered content — no existing chunking strategy makes that cheap to
 * guarantee in e2e; it is covered by the unit suite (T3-AC5). The realized
 * two skip classes carry the same idempotence contract that the M2 fix
 * relies on.
 */

import * as crypto from 'crypto';
import * as fs from 'fs/promises';
import * as path from 'path';
import { ForceReprocessService } from '../../application/services/force-reprocess.service';
import { FILE_TRACKER_SKIP_REASON } from '../../domain/file-tracker.aggregate';
import type { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { PrismaService } from '../../infrastructure/prisma/prisma.service';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { cleanupTempDir, createTempDir } from '../e2e-utils';
import { createTestApplication } from '../main.test-application';

const SOURCE_ID = 'e2e-never-ingestable-source';
const MEMORY_BANK = 'e2e-test-ns';

// Mirrors DEFAULT_CONTENT_FILTER_OPTIONS.maxLineLength (content-classifier):
// one line of 100_001 chars deterministically trips the `long-line` trigger,
// no LLM involved.
const FILTERED_LINE = 'x'.repeat(100_001);

interface CorpusFile {
  fileName: string;
  content: string;
  /** Terminal skip the row must carry; null ⇒ the file must be ingested. */
  expectedSkipReason: string | null;
  filePath: string;
  expectedHash: string;
}

/** Full observable state of one corpus file across runs. */
interface FileStateSnapshot {
  trackerId: string;
  fileHash: string | null;
  skipReason: string | null;
  updatedAtMs: number;
  memoryRowCount: number;
  bankChunkCount: number;
}

const sha256 = (content: string): string => crypto.createHash('sha256').update(content).digest('hex');

describe('[E2E] Never-ingestable quarantine — terminal skips on run 1, zero chunk ops on run 2', () => {
  const uniqueId = Date.now();
  const marker = `NEVERING-${uniqueId}`;

  let app: Awaited<ReturnType<typeof createTestApplication>> | null = null;
  let forceReprocessService: ForceReprocessService | null = null;
  let bensyneClient: BensyneClient | null = null;
  let prisma: PrismaService | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let corpusDir: string | null = null;

  // Shared between the two sequential tests (maxWorkers: 1).
  let corpus: CorpusFile[] = [];
  let testSource: WatchSourceConfig | null = null;
  let healthyFilePath = '';

  const healthyContent = () =>
    `# Never-Ingestable Control Note ${uniqueId}\n\n` +
    `This ordinary note exists to prove the reconciliation pass still ingests NEW` +
    ` work next to quarantined files, and skips it as verified on the second pass.` +
    ` Marker: ${marker}. It has normal prose diversity and short lines, so the` +
    ` classifier accepts it and the chunker produces at least one chunk.`;

  beforeAll(async () => {
    corpusDir = await createTempDir('rag-e2e-nevering-');

    corpus = [
      {
        fileName: 'zero-byte.md',
        content: '',
        expectedSkipReason: FILE_TRACKER_SKIP_REASON.EMPTY_CONTENT,
        filePath: path.join(corpusDir, 'zero-byte.md'),
        expectedHash: sha256(''),
      },
      {
        fileName: 'whitespace-only.md',
        content: '   \n\t \n  \n',
        expectedSkipReason: FILE_TRACKER_SKIP_REASON.EMPTY_CONTENT,
        filePath: path.join(corpusDir, 'whitespace-only.md'),
        expectedHash: sha256('   \n\t \n  \n'),
      },
      {
        fileName: 'machine-dump.txt',
        content: FILTERED_LINE,
        expectedSkipReason: FILE_TRACKER_SKIP_REASON.CONTENT_FILTERED,
        filePath: path.join(corpusDir, 'machine-dump.txt'),
        expectedHash: sha256(FILTERED_LINE),
      },
    ];
    healthyFilePath = path.join(corpusDir, `healthy-note-${uniqueId}.md`);

    for (const file of corpus) {
      await fs.writeFile(file.filePath, file.content, 'utf-8');
    }
    await fs.writeFile(healthyFilePath, healthyContent(), 'utf-8');

    app = await createTestApplication();
    await app.init();

    // Hermetic source: derived from the real boot-resolved source shape
    // (fully-defaulted WatchSourceConfig, incl. DEFAULT_CONTENT_FILTER_OPTIONS
    // that the filtered fixture below relies on) — but pointed at the temp
    // corpus and NOT registered in config, so no watcher ever sees this dir.
    const template = app
      .get(ConfigurationService)
      .getWatchSources()
      .find(s => s.id === 'e2e-test-source');
    expect(template).toBeDefined();
    testSource = {
      ...template!,
      id: SOURCE_ID,
      path: corpusDir,
      resolvedPaths: [corpusDir],
      exclude: [],
      memoryBank: MEMORY_BANK,
      autoPopulate: true,
    };

    forceReprocessService = app.get(ForceReprocessService);
    bensyneClient = app.get(BensyneClient);
    prisma = app.get(PrismaService);
    processingQueue = app.get(FileProcessingQueue);
  }, 90000);

  afterAll(async () => {
    // Remove only THIS suite's rows from the shared tracker DB (same cleanup
    // style the recover-mode suite applies to its own source id), then the
    // corpus dir, then the app.
    if (prisma != null) {
      try {
        const rows = await prisma.fileTracker.findMany({
          where: { sourceId: SOURCE_ID },
          select: { id: true },
        });
        const ids = rows.map(r => r.id);
        if (ids.length > 0) {
          await prisma.fileMemoryTracker.deleteMany({ where: { fileTrackerId: { in: ids } } });
          await prisma.fileTracker.deleteMany({ where: { id: { in: ids } } });
        }
      } catch {
        // Best-effort cleanup — never mask the original failure.
      }
    }
    if (corpusDir != null) {
      await cleanupTempDir(corpusDir);
    }
    if (app != null) {
      await app.close().catch(() => undefined);
    }
  });

  async function bankChunkCount(filePath: string): Promise<number> {
    const result = await bensyneClient!.getFileChunks(filePath, MEMORY_BANK);
    expect(result.isOk()).toBe(true);
    return result.getValue().chunks.length;
  }

  async function snapshotFile(filePath: string): Promise<FileStateSnapshot> {
    const row = await prisma!.fileTracker.findUnique({ where: { filePath } });
    expect(row).not.toBeNull();
    const memoryRowCount = await prisma!.fileMemoryTracker.count({
      where: { fileTrackerId: row!.id },
    });
    return {
      trackerId: row!.id.toString(),
      fileHash: row!.fileHash,
      skipReason: row!.skipReason,
      updatedAtMs: row!.updatedAt.getTime(),
      memoryRowCount,
      bankChunkCount: await bankChunkCount(filePath),
    };
  }

  it('run 1: never-ingestable files record terminal skip rows with zero memories; the ordinary note is fully ingested', async () => {
    const summary = await forceReprocessService!.autoPopulateSources([testSource!]);
    await processingQueue!.waitForEmpty();

    // Exact, hermetic counters: first pass = 3 terminal skips + 1 real ingest.
    expect(summary).toEqual({
      files: 4,
      gatedSkips: 0,
      terminalSkipSkips: 3,
      verifiedSkips: 0,
      reIngested: 1,
    });

    for (const file of corpus) {
      const row = await prisma!.fileTracker.findUnique({ where: { filePath: file.filePath } });
      expect(row).not.toBeNull();
      expect(row!.skipReason).toBe(file.expectedSkipReason);
      expect(row!.fileHash).toBe(file.expectedHash);
      const memoryCount = await prisma!.fileMemoryTracker.count({
        where: { fileTrackerId: row!.id },
      });
      expect(memoryCount).toBe(0);
      // No chunk work reached the bank for a never-ingestable file.
      expect(await bankChunkCount(file.filePath)).toBe(0);
      console.log(
        `[E2E-NeverIngestable] ${file.fileName}: skipReason=${row!.skipReason}, memories=0, bankChunks=0`,
      );
    }

    const healthyRow = await prisma!.fileTracker.findUnique({
      where: { filePath: healthyFilePath },
    });
    expect(healthyRow).not.toBeNull();
    expect(healthyRow!.skipReason).toBeNull();
    expect(healthyRow!.fileHash).toBe(sha256(healthyContent()));
    const healthyMemories = await prisma!.fileMemoryTracker.count({
      where: { fileTrackerId: healthyRow!.id },
    });
    expect(healthyMemories).toBeGreaterThan(0);
    expect(await bankChunkCount(healthyFilePath)).toBeGreaterThan(0);
    console.log(`[E2E-NeverIngestable] ordinary note: memories=${healthyMemories}, ingested normally`);
  }, 240000);

  it('run 2 (re-reconcile): new-files-only queue structurally empty — all-zero summary, zero chunk ops, state identical', async () => {
    // Capture every observable BEFORE the second pass.
    const before = new Map<string, FileStateSnapshot>();
    for (const file of corpus) {
      before.set(file.fileName, await snapshotFile(file.filePath));
    }
    const healthyBefore = await snapshotFile(healthyFilePath);

    const summary = await forceReprocessService!.autoPopulateSources([testSource!]);
    await processingQueue!.waitForEmpty();

    // Exact, hermetic counters for the second pass, re-baselined per DEC-A7
    // (AMENDED 2026-11-02): resume/auto-populate queues NEW FILES ONLY —
    // every corpus file has a FileTracker row by now (terminal-skip rows ARE
    // rows), so the queue is EMPTY up front. Nothing reaches the gate, the
    // bank, or the LLM: the returned DATA is all zero, files=0 being the
    // healthy repeat-run signature.
    expect(summary).toEqual({
      files: 0,
      gatedSkips: 0,
      terminalSkipSkips: 0,
      verifiedSkips: 0,
      reIngested: 0,
    });

    for (const file of corpus) {
      const after = await snapshotFile(file.filePath);
      // Zero chunk operations, zero re-decisions: every observable identical
      // — including updatedAt (the gate performs no write at all).
      expect(after).toEqual(before.get(file.fileName));
      expect(after.bankChunkCount).toBe(0);
      console.log(
        `[E2E-NeverIngestable] run2 ${file.fileName}: unchanged (skipReason=${after.skipReason}, bankChunks=0, updatedAtMs=${after.updatedAtMs})`,
      );
    }

    const healthyAfter = await snapshotFile(healthyFilePath);
    expect(healthyAfter).toEqual(healthyBefore);
    console.log('[E2E-NeverIngestable] run2 ordinary note: unchanged (verified-skip path)');
  }, 240000);
});
