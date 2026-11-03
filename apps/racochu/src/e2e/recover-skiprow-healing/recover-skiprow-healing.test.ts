/**
 * [E2E] Recover × skip-row healing — the VERIFY-CARRYING pin of DEC-A7
 * guarantee (c) (spec §8 "NEW recover-skiprow-healing.spec"; mechanism note C4:
 * "carried by recover step-4 FILE_NOT_FOUND force path — NEVER step-5").
 *
 * Contract under test (DEC-A7, AMENDED 2026-11-02): a terminal-skip row is
 * terminal ONLY for that exact content hash. When the file's content CHANGES,
 * `--recover` — the sole reconciler — must heal it: the row enters the
 * decision table via findTrackedBySourceId, its absent bank side puts it on
 * step 4 (FILE_NOT_FOUND → forceIngest re-evaluation), the re-classified
 * content passes every skip branch, and the successful ingest writes the NEW
 * fileHash and clears skipReason (C3.5 clear-on-ingest path).
 *
 * HERMETIC source by construction (never-ingestable idiom): the fixture lives
 * in a temp dir OUTSIDE the e2e config watch sources; the explicit
 * WatchSourceConfig is passed directly to the services. No chokidar watcher
 * ever sees the dir (no watcher race), nothing else shares the corpus, so
 * every counter below is EXACT and the scenario ORDER is the proof structure:
 *
 * PHASE 1 — first reconciliation pass (`autoPopulateSources([testSource])`):
 *   - the 0-byte fixture records a terminal skip: FileTracker row with
 *     skipReason='empty-content' (hash = sha256('')), zero FileMemoryTracker
 *     rows, zero bank chunks; summary DATA pins the skip (terminalSkipSkips=1).
 *   ⇒ proves the PRE-EXISTING skip-row before any change (RED-trail point).
 * PHASE 2 — rewrite the fixture with real, acceptable content (hash changes),
 * then run recover (`recoverService.recoverSource(SOURCE_ID, [testSource])`,
 * the in-process twin of the `--recover` CLI — same wiring as main.ts):
 *   - memories now exist for the file: local FileMemoryTracker rows > 0 and
 *     bank chunks via getFileChunks > 0 (bank observation),
 *   - the FileTracker row carries skipReason = null and a FRESH fileHash
 *     equal to sha256(newContent).
 *
 * STOP condition (Task 12): this scenario is the amendment's verify-carrying
 * pin — no product code here. If it fails on product behavior, it is a
 * product defect to report, not something to code around.
 */

import * as crypto from 'crypto';
import * as fs from 'fs/promises';
import * as path from 'path';
import { ForceReprocessService } from '../../application/services/force-reprocess.service';
import { RecoverService } from '../../application/services/recover.service';
import { FILE_TRACKER_SKIP_REASON } from '../../domain/file-tracker.aggregate';
import type { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { PrismaService } from '../../infrastructure/prisma/prisma.service';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { cleanupTempDir, createTempDir } from '../e2e-utils';
import { createTestApplication } from '../main.test-application';

const SOURCE_ID = 'e2e-skiprow-heal-source';
const MEMORY_BANK = 'e2e-test-ns';

// Debounce(500ms) + chunking + MCP ingestion + Mnemosyne indexing
// (same waits the recover-mode suite uses for bank-side visibility).
const PROCESSING_WAIT_MS = 20000;

const sha256 = (content: string): string => crypto.createHash('sha256').update(content).digest('hex');

describe('[E2E] Recover skip-row healing — DEC-A7 (c): changed skip-row is reconciled by --recover (step-4 force path)', () => {
  const uniqueId = Date.now();
  const marker = `SKIPHEAL-${uniqueId}`;

  let app: Awaited<ReturnType<typeof createTestApplication>> | null = null;
  let forceReprocessService: ForceReprocessService | null = null;
  let recoverService: RecoverService | null = null;
  let bensyneClient: BensyneClient | null = null;
  let prisma: PrismaService | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let corpusDir: string | null = null;

  // Shared between the two sequential tests (maxWorkers: 1) — the scenario
  // order IS the proof: phase 1 observes the skip-row BEFORE the change.
  let testSource: WatchSourceConfig | null = null;
  let fixturePath = '';

  // Real, classifiable content with normal prose diversity and short lines —
  // the same acceptance profile the never-ingestable healthy note uses, so the
  // classifier accepts it and the chunker produces at least one chunk.
  const healedContent = () =>
    `# Skip-Row Healing Note ${uniqueId}\n\n` +
    `This file was a 0-byte fixture whose first pass recorded a terminal skip row. ` +
    `It has since been rewritten with real content, so its hash no longer matches ` +
    `the recorded skip. Marker: ${marker}. Recover is expected to notice the file ` +
    `is absent from the bank side, force-reevaluate the new bytes past every skip ` +
    `branch, ingest it fully, write the fresh hash, and clear the skip reason.`;

  beforeAll(async () => {
    corpusDir = await createTempDir('rag-e2e-skipheal-');
    fixturePath = path.join(corpusDir, `heal-me-${uniqueId}.md`);
    await fs.writeFile(fixturePath, '', 'utf-8');

    app = await createTestApplication();
    await app.init();

    // Hermetic source: derived from the real boot-resolved source shape
    // (fully-defaulted WatchSourceConfig incl. DEFAULT_CONTENT_FILTER_OPTIONS),
    // pointed at the temp fixture dir and NOT registered in config — no
    // watcher ever sees this dir (Ad-Hoc A pattern: no watcher race).
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
    recoverService = app.get(RecoverService);
    bensyneClient = app.get(BensyneClient);
    prisma = app.get(PrismaService);
    processingQueue = app.get(FileProcessingQueue);
  }, 90000);

  afterAll(async () => {
    // Remove only THIS suite's rows from the shared tracker DB, then the
    // fixture dir, then the app (never-ingestable cleanup style).
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

  it('phase 1: the 0-byte fixture records a terminal skip row (existing before the change) with zero memories and zero bank chunks', async () => {
    const summary = await forceReprocessService!.autoPopulateSources([testSource!]);
    await processingQueue!.waitForEmpty();

    // Exact, hermetic counters: single-file private source = one terminal skip.
    expect(summary).toEqual({
      files: 1,
      gatedSkips: 0,
      terminalSkipSkips: 1,
      verifiedSkips: 0,
      reIngested: 0,
    });

    const row = await prisma!.fileTracker.findUnique({ where: { filePath: fixturePath } });
    expect(row).not.toBeNull();
    expect(row!.skipReason).toBe(FILE_TRACKER_SKIP_REASON.EMPTY_CONTENT);
    expect(row!.fileHash).toBe(sha256(''));
    const memoryCount = await prisma!.fileMemoryTracker.count({
      where: { fileTrackerId: row!.id },
    });
    expect(memoryCount).toBe(0);
    expect(await bankChunkCount(fixturePath)).toBe(0);
    console.log(
      `[E2E-SkipRowHealing] phase1 skip-row recorded: skipReason=${row!.skipReason}, fileHash=${row!.fileHash}, memories=0, bankChunks=0`,
    );
  }, 240000);

  it('phase 2: real content + --recover ⇒ memories exist, skipReason cleared, fresh fileHash (step-4 force path — DEC-A7 (c))', async () => {
    const newContent = healedContent();
    await fs.writeFile(fixturePath, newContent, 'utf-8');
    // The precondition of the guarantee: the recorded hash no longer matches.
    expect(sha256(newContent)).not.toBe(sha256(''));

    console.log('[E2E-SkipRowHealing] phase2 running recoverSource (the --recover duty)…');
    await recoverService!.recoverSource(SOURCE_ID, [testSource!]);
    await processingQueue!.waitForEmpty();
    await new Promise(r => setTimeout(r, PROCESSING_WAIT_MS));

    // Bank observation point 1: chunks now exist for the file.
    const chunks = await bankChunkCount(fixturePath);
    expect(chunks).toBeGreaterThan(0);

    // DB observation point 2: local memory tracking exists for the row.
    const row = await prisma!.fileTracker.findUnique({ where: { filePath: fixturePath } });
    expect(row).not.toBeNull();
    const memoryCount = await prisma!.fileMemoryTracker.count({
      where: { fileTrackerId: row!.id },
    });
    expect(memoryCount).toBeGreaterThan(0);

    // DB observation point 3: the healed row — skip cleared + fresh hash (C3.5
    // clear-on-ingest via trackMemory → updateFileTrackerHash).
    expect(row!.skipReason).toBeNull();
    expect(row!.fileHash).toBe(sha256(newContent));

    console.log(
      `[E2E-SkipRowHealing] phase2 healed: bankChunks=${chunks}, memories=${memoryCount}, skipReason=null, fileHash=${row!.fileHash}`,
    );
  }, 240000);
});
