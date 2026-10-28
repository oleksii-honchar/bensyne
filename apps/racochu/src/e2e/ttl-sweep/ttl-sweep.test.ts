import { FileProcessingQueue } from '@/infrastructure/services/file-processing-queue.service';
import { INestApplication } from '@nestjs/common';
import * as fsSync from 'fs';
import * as fs from 'fs/promises';
import { DatabaseSync } from 'node:sqlite';
import * as path from 'path';
import { ForceReprocessService } from '../../application/services/force-reprocess.service';
import { TtlReconciliationService } from '../../application/services/ttl-reconciliation.service';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { PrismaService } from '../../infrastructure/prisma/prisma.service';
import { FileMemoryTrackerRepository } from '../../infrastructure/repositories/file-memory-tracker.repository';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { createTestApplication } from '../main.test-application';

const PROCESSING_WAIT_MS = 20000; // debounce(500ms) + chunking + MCP ingestion + Mnemosyne indexing
const SETTLE_WAIT_MS = 5000; // zero-work window: drain check + quiet period before asserting "nothing happened"
const MS_PER_DAY = 86_400_000;
const TTL_DAYS = 365;
const BACKDATE_DAYS = 400; // 400 > 365 → definitely expired
const REVIVE_AGE_DAYS = 40; // §7(5) fixture: mtime older than the source's 30-day window
const REVIVE_TTL_DAYS = 30;

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

  // Shared across the sequential tests in this file (maxWorkers: 1).
  let uniqueId: number;
  let marker: string;
  let filePath: string;

  // Feature-matrix state (spec §7 items 1–9, the tests numbered 4–12 below).
  // Their files live under a private scope root beside the watch dirs —
  // never watched, so ONLY the explicit service calls below touch them.
  let forceReprocessService: ForceReprocessService | null = null;
  let scopeRoot: string | undefined;
  let ttlSource: WatchSourceConfig | undefined;
  let obsidianSource: WatchSourceConfig | undefined;
  // Chain shared by §7(1)–(4) (test 4 seeds it; tests 5–7 continue on it).
  let chainScope: WatchSourceConfig | undefined;
  let chainFileA: string;
  let chainFileB: string;
  let chainMarkerA: string;
  let chainMarkerB: string;

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

  // ── §7 feature-matrix helpers ────────────────────────────────────────────────
  // A scoped source VIEW of a declared source: same id/memory-bank (so its
  // rows are the ones the real sweep reconciles), but enumeration rooted at a
  // private directory. The services consume the passed config object, so no
  // global config change is needed. `resolvedPaths` is overridden alongside
  // `path` because declaredRoots prefers the normalized form.
  function scopedSource(
    base: WatchSourceConfig,
    subDir: string,
    overrides: Partial<WatchSourceConfig> = {},
  ): WatchSourceConfig {
    const dir = path.join(scopeRoot!, subDir);
    return { ...base, path: dir, resolvedPaths: [dir], ...overrides };
  }

  /** Age the file's LAST-ACTIVITY clock (its mtime) past its true age. */
  async function ageFile(targetPath: string, ageDays: number): Promise<void> {
    const agedAt = new Date(Date.now() - ageDays * MS_PER_DAY);
    await fs.utimes(targetPath, agedAt, agedAt);
    const stat = await fs.stat(targetPath);
    const actualAgeDays = (Date.now() - stat.mtimeMs) / MS_PER_DAY;
    expect(actualAgeDays).toBeGreaterThan(ageDays - 1);
    console.log(`[E2E-TtlSweep] Aged file mtime: ${targetPath} (${Math.round(actualAgeDays)}d)`);
  }

  /** Real update: a genuine touch — the activity clock restarts here. */
  function touchFileNow(targetPath: string): void {
    const now = new Date();
    fsSync.utimesSync(targetPath, now, now);
    console.log(`[E2E-TtlSweep] Touched file (real update): ${targetPath}`);
  }

  async function writeScopedFile(scoped: WatchSourceConfig, name: string, content: string): Promise<string> {
    await fs.mkdir(scoped.path!, { recursive: true });
    const targetPath = path.join(scoped.path!, name);
    await fs.writeFile(targetPath, content, 'utf-8');
    return targetPath;
  }

  /** Run a batch/explicit operation and drain the processing pipeline. */
  async function runAndDrain(work: () => Promise<void>): Promise<void> {
    await work();
    await processingQueue!.waitForEmpty();
    await new Promise(resolve => setTimeout(resolve, SETTLE_WAIT_MS));
    await processingQueue!.waitForEmpty();
  }

  /** Explicit-door initial ingestion (B5 never consults the gate). */
  async function ingestViaExplicitDoor(scoped: WatchSourceConfig): Promise<void> {
    await runAndDrain(() => forceReprocessService!.forceReprocessSource(SOURCE_ID, [scoped]));
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();
  }

  async function trackerCountFor(targetPath: string): Promise<number> {
    return prisma!.fileTracker.count({ where: { filePath: targetPath } });
  }

  async function memoryRowsFor(targetPath: string): Promise<number> {
    const row = await prisma!.fileTracker.findFirst({ where: { filePath: targetPath } });
    if (row === null) {
      return 0;
    }
    return prisma!.fileMemoryTracker.count({ where: { fileTrackerId: row.id } });
  }

  async function bankHasMarker(markerText: string, bank: string = MEMORY_BANK): Promise<boolean> {
    const result = await bensyneClient!.recall(markerText, 5, 1000, bank);
    expect(result.isOk()).toBe(true);
    return result.getValue().some(r => r.content.includes(markerText));
  }

  async function bankChunkCount(targetPath: string, bank: string = MEMORY_BANK): Promise<number> {
    const result = await bensyneClient!.getFileChunks(targetPath, bank);
    expect(result.isOk()).toBe(true);
    return result.getValue().chunks.length;
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
    forceReprocessService = app.get(ForceReprocessService);

    // §7 feature-matrix scaffolding: config-declared source views plus a
    // private scope root beside the watch dirs. Nothing watches the scope
    // dirs, so ONLY the explicit service calls below can touch their files.
    const configuredSources = configurationService!.getWatchSources();
    ttlSource = configuredSources.find(s => s.id === SOURCE_ID);
    obsidianSource = configuredSources.find(s => s.id === OBSIDIAN_SOURCE_ID);
    expect(ttlSource).toBeDefined();
    expect(obsidianSource).toBeDefined();
    expect(ttlSource!.ttlDays).toBe(TTL_DAYS);
    expect(obsidianSource!.ttlDays).toBeUndefined();
    scopeRoot = path.join(path.dirname(watchDir!), 'ttl-activity-scope');
    await fs.mkdir(scopeRoot, { recursive: true });
    console.log(`[E2E-TtlSweep] Feature-matrix scope root: ${scopeRoot}`);

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
    // Feature-matrix scope files live OUTSIDE the shared watch dirs — clean
    // them here so they cannot leak into any later suite's store counts.
    await fs.rm(scopeRoot!, { recursive: true, force: true }).catch(() => undefined);
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
    // Age the file's ACTIVITY CLOCK past the 365-day TTL (400 days of mtime).
    // Provenance (spec §3.4 item 4, ADR-8/ADR-9): this fixture previously
    // backdated the tracker row `createdAt` — that SQL-era clock was
    // superseded by the activity clock (mtime is authoritative for present
    // files; createdAt is audit-only). The pinned coverage — dry-run counts +
    // "dry run deletes nothing" — is unchanged; only the fixture clock moved.
    await ageFile(filePath, BACKDATE_DAYS);
    // Ages-only change: drain any watcher echo of the utimes touch so the
    // sweep sees a quiet queue (the batch-path gate may also skip it — fine,
    // the sweep is row-driven and the file is never removed here).
    await new Promise(resolve => setTimeout(resolve, 2000));
    await processingQueue!.waitForEmpty();

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

  // ── Feature matrix — spec §7 items 1–9 (activity-gate end-to-end) ──────────
  // Tests 4–12 implement §7(1)–(9). Their files live in private scope dirs
  // (see `scopedSource`), touched ONLY by the batch/explicit service calls
  // under test — never by a watcher — so row/memory counts stay exact.
  // Tests 4–7 form one §7-chain (the spec's items reference each other);
  // tests 8–12 pin independent fresh sets.

  it('4. §7(1) sweep-then-resume zero — a forgotten file is never re-ingested by a batch pass', async () => {
    chainScope = scopedSource(ttlSource!, 'chain');
    const uniqueId = Date.now();
    chainMarkerA = `TTL-CHAIN-A-${uniqueId}`;
    chainMarkerB = `TTL-CHAIN-B-${uniqueId}`;
    chainFileA = await writeScopedFile(
      chainScope,
      'chain-a.md',
      `# TTL Chain A ${uniqueId}\n\nMarker: ${chainMarkerA}. Past-due after the sweep; batch paths must never re-ingest it.`,
    );
    chainFileB = await writeScopedFile(
      chainScope,
      'chain-b.md',
      `# TTL Chain B ${uniqueId}\n\nMarker: ${chainMarkerB}. Second file of the past-due set N=2.`,
    );

    // Ingest N=2 files via the explicit door (B5 is un-gated today).
    await ingestViaExplicitDoor(chainScope);
    expect(await trackerCountFor(chainFileA)).toBe(1);
    expect(await trackerCountFor(chainFileB)).toBe(1);
    expect(await memoryRowsFor(chainFileA)).toBeGreaterThan(0);
    expect(await bankHasMarker(chainMarkerA)).toBe(true);
    expect(await bankHasMarker(chainMarkerB)).toBe(true);

    // Age the set past the source's ttlDays via the fixture clock (utimes).
    await ageFile(chainFileA, BACKDATE_DAYS);
    await ageFile(chainFileB, BACKDATE_DAYS);

    // Real sweep: exactly this aged set is forgotten; terminal behavior is
    // asserted unchanged (B1 — hard-delete of the row, bank forget, tombstone).
    const summary = await ttlService!.run();
    console.log(`[E2E-TtlSweep] §7(1) sweep summary: ${JSON.stringify(summary)}`);
    expect(summary.sourcesChecked).toBe(1);
    expect(summary.expired).toBe(2);
    expect(summary.forgotten).toBe(2);
    expect(summary.failed).toBe(0);
    expect(await trackerCountFor(chainFileA)).toBe(0);
    expect(await trackerCountFor(chainFileB)).toBe(0);
    expect(await memoryRowsFor(chainFileA)).toBe(0);
    expect(await bankHasMarker(chainMarkerA)).toBe(false);
    expect(await bankHasMarker(chainMarkerB)).toBe(false);
    const db = openFileMetadataDb();
    try {
      const fileRow = findFileRow(db, chainFileA);
      expect(fileRow).toBeDefined();
      expect(fileRow!.status).toBe('deleted');
      expect(countChunksForFile(db, fileRow!.id)).toBe(0);
    } finally {
      db.close();
    }

    // resumeSource over the enumerated set (all that remains is the disk):
    // ZERO new FileTracker/FileMemoryTracker rows, zero memories.
    await runAndDrain(() => forceReprocessService!.resumeSource(SOURCE_ID, [chainScope!]));
    expect(await trackerCountFor(chainFileA)).toBe(0);
    expect(await trackerCountFor(chainFileB)).toBe(0);
    expect(await bankChunkCount(chainFileA)).toBe(0);
    expect(await bankChunkCount(chainFileB)).toBe(0);
    expect(await bankHasMarker(chainMarkerA)).toBe(false);

    // Production-path fidelity: a REAL-source resume (what `racochu --resume`
    // enumerates: the watched dir, incl. the aged test-1 file) also revives
    // none of these paths. Other recent files of earlier suites may verify/
    // re-ingest — that is today's untouched behavior and out of scope here.
    await runAndDrain(() => forceReprocessService!.resumeSource(SOURCE_ID, [ttlSource!]));
    expect(await trackerCountFor(chainFileA)).toBe(0);
    expect(await trackerCountFor(chainFileB)).toBe(0);
    expect(await trackerCountFor(filePath!)).toBe(0);
    expect(await bankHasMarker(marker!)).toBe(false);
  }, 420000);

  it('5. §7(2) explicit door after a forget — byte-identical D21 resurrection, fresh row and retention', async () => {
    // §7(2) runs after §7(1) (spec cross-reference): chainFileA is past-due
    // with NO row. The explicit single-file door never consults the gate.
    expect(await trackerCountFor(chainFileA!)).toBe(0);

    await runAndDrain(() => forceReprocessService!.forceReprocessFile(chainFileA!, chainScope!));
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();

    // Fresh row (fresh createdAt → fresh full retention window) + full bank
    // presence again — exactly today's hard-delete→recreate semantics.
    const row = await prisma!.fileTracker.findFirst({ where: { filePath: chainFileA } });
    expect(row).not.toBeNull();
    expect(Date.now() - row!.createdAt.getTime()).toBeLessThan(120_000);
    expect(await memoryRowsFor(chainFileA)).toBeGreaterThan(0);
    expect(await bankHasMarker(chainMarkerA!)).toBe(true);
    expect(await bankChunkCount(chainFileA)).toBeGreaterThan(0);
    const db = openFileMetadataDb();
    try {
      const fileRow = findFileRow(db, chainFileA);
      expect(fileRow).toBeDefined();
      expect(fileRow!.status).toBe('indexed'); // D21: DELETED → INDEXED again
      expect(countChunksForFile(db, fileRow!.id)).toBeGreaterThan(0);
    } finally {
      db.close();
    }
    // The door is path-targeted: the sibling stayed forgotten.
    expect(await trackerCountFor(chainFileB!)).toBe(0);
    expect(await bankHasMarker(chainMarkerB!)).toBe(false);
  }, 180000);

  it('6. §7(3) repeat resume — still zero (idempotent w.r.t. restarts)', async () => {
    // State: chainFileA has a live row (from the §7(2) door) but an aged
    // mtime; chainFileB has nothing. A repeated batch pass must add ZERO.
    const rowBefore = await prisma!.fileTracker.findFirst({ where: { filePath: chainFileA! } });
    expect(rowBefore).not.toBeNull();
    const memBefore = await memoryRowsFor(chainFileA!);
    const chunksBefore = await bankChunkCount(chainFileA!);
    expect(await trackerCountFor(chainFileB!)).toBe(0);

    await runAndDrain(() => forceReprocessService!.resumeSource(SOURCE_ID, [chainScope!]));

    const rowAfter = await prisma!.fileTracker.findFirst({ where: { filePath: chainFileA! } });
    expect(rowAfter!.id).toBe(rowBefore!.id); // same row — no recreate work
    expect(rowAfter!.createdAt.getTime()).toBe(rowBefore!.createdAt.getTime());
    expect(await memoryRowsFor(chainFileA!)).toBe(memBefore); // no duplicate ingest
    expect(await bankChunkCount(chainFileA!)).toBe(chunksBefore);
    expect(await trackerCountFor(chainFileB!)).toBe(0);
    expect(await bankHasMarker(chainMarkerB!)).toBe(false);
  }, 120000);

  it('7. §7(4) auto-populate over the same past-due set — zero ingests', async () => {
    // Startup auto-population shares the resume loop (B14a) — same rule.
    const rowBefore = await prisma!.fileTracker.findFirst({ where: { filePath: chainFileA! } });
    expect(rowBefore).not.toBeNull();
    const memBefore = await memoryRowsFor(chainFileA!);
    expect(await trackerCountFor(chainFileB!)).toBe(0);

    await runAndDrain(() => forceReprocessService!.autoPopulateSources([chainScope!]));

    const rowAfter = await prisma!.fileTracker.findFirst({ where: { filePath: chainFileA! } });
    expect(rowAfter!.id).toBe(rowBefore!.id);
    expect(await memoryRowsFor(chainFileA!)).toBe(memBefore);
    expect(await trackerCountFor(chainFileB!)).toBe(0);
    expect(await bankHasMarker(chainMarkerB!)).toBe(false);
  }, 120000);

  it('8. §7(5) never-tracked past-due file — resume zero; a real update restores eligibility', async () => {
    // Spec-faithful fixture: 40-day-old mtime, ttlDays: 30, NO DB row at all.
    const reviveScope = scopedSource(ttlSource!, 'revive', { ttlDays: REVIVE_TTL_DAYS });
    const uniqueId = Date.now();
    const reviveMarker = `TTL-REVIVE-${uniqueId}`;
    const reviveFile = await writeScopedFile(
      reviveScope,
      'never-tracked.md',
      `# Never Tracked ${uniqueId}\n\nMarker: ${reviveMarker}. Activity-gated before it was ever known.`,
    );
    await ageFile(reviveFile, REVIVE_AGE_DAYS);
    expect(await trackerCountFor(reviveFile)).toBe(0);

    await runAndDrain(() => forceReprocessService!.resumeSource(SOURCE_ID, [reviveScope]));

    // Skipped BEFORE any getMemoryIds/verify/ingest work — the zero-work
    // effect is the assertion; the skip notice itself is pinned at the unit
    // layer (Task 2) and is only an optional log here (§7(5)).
    expect(await trackerCountFor(reviveFile)).toBe(0);
    expect(await bankChunkCount(reviveFile)).toBe(0);
    expect(await bankHasMarker(reviveMarker)).toBe(false);

    // A real update (utimes to now) IS the activity clock — next resume
    // ingests fully. No stored eligibility state is involved.
    touchFileNow(reviveFile);
    await runAndDrain(() => forceReprocessService!.resumeSource(SOURCE_ID, [reviveScope]));
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();

    expect(await trackerCountFor(reviveFile)).toBe(1);
    expect(await memoryRowsFor(reviveFile)).toBeGreaterThan(0);
    expect(await bankHasMarker(reviveMarker)).toBe(true);
  }, 240000);

  it('9. §7(6) active file never prematurely forgotten — survives N=3 sweep cycles while touched', async () => {
    // Retires the Spec-0006 accepted risk: clock = last update, so a file
    // touched before every sweep can never expire.
    const aliveScope = scopedSource(ttlSource!, 'alive');
    const uniqueId = Date.now();
    const aliveMarker = `TTL-ALIVE-${uniqueId}`;
    const aliveFile = await writeScopedFile(
      aliveScope,
      'alive.md',
      `# Active File ${uniqueId}\n\nMarker: ${aliveMarker}. Touched before every sweep — must never be forgotten.`,
    );
    await ingestViaExplicitDoor(aliveScope);
    const row0 = await prisma!.fileTracker.findFirst({ where: { filePath: aliveFile } });
    expect(row0).not.toBeNull();
    const mem0 = await memoryRowsFor(aliveFile);

    // Only chainFileA from §7(2) is past-due-tracked when these cycles run:
    // cycle 1 forgets exactly that one, cycles 2–3 find nothing.
    for (let cycle = 1; cycle <= 3; cycle++) {
      touchFileNow(aliveFile); // touched before each forced daily sweep
      const summary = await ttlService!.run();
      console.log(`[E2E-TtlSweep] §7(6) cycle ${cycle}: ${JSON.stringify(summary)}`);
      expect(summary.failed).toBe(0);
      expect(summary.refusedMassForget).toBe(0);
      expect(summary.expired).toBe(cycle === 1 ? 1 : 0);
      // The active file survives every cycle untouched — same row, never
      // forgot, despite sweeps that DID run and forget other files.
      const row = await prisma!.fileTracker.findFirst({ where: { filePath: aliveFile } });
      expect(row).not.toBeNull();
      expect(row!.createdAt.getTime()).toBe(row0!.createdAt.getTime());
    }
    expect(await memoryRowsFor(aliveFile)).toBe(mem0);
    expect(await bankHasMarker(aliveMarker)).toBe(true);
  }, 180000);

  it('10. §7(7) legacy hard-deleted row + past-due file — resume is a no-op (no migration)', async () => {
    // Pre-feature state, re-created on purpose: forget + hard-delete a row
    // as the terminal ops have always done, with the file left on disk and
    // past due. The feature must treat it like any past-due file: zero.
    const legacyScope = scopedSource(ttlSource!, 'legacy');
    const uniqueId = Date.now();
    const legacyMarker = `TTL-LEGACY-${uniqueId}`;
    const legacyFile = await writeScopedFile(
      legacyScope,
      'legacy.md',
      `# Legacy State ${uniqueId}\n\nMarker: ${legacyMarker}. Row deleted "the old way".`,
    );
    await ingestViaExplicitDoor(legacyScope);
    expect(await trackerCountFor(legacyFile)).toBe(1);
    await ageFile(legacyFile, BACKDATE_DAYS);

    const forgetResult = await bensyneClient!.forgetByFile(legacyFile, MEMORY_BANK);
    expect(forgetResult.isOk()).toBe(true);
    await prisma!.fileTracker.delete({ where: { filePath: legacyFile } }); // old-way hard delete (memories cascade)
    expect(await trackerCountFor(legacyFile)).toBe(0);
    await new Promise(resolve => setTimeout(resolve, 2000));
    await processingQueue!.waitForEmpty();
    expect(await bankHasMarker(legacyMarker)).toBe(false);

    await runAndDrain(() => forceReprocessService!.resumeSource(SOURCE_ID, [legacyScope]));

    // Zero re-creation — legacy state needs no migration and no wave.
    expect(await trackerCountFor(legacyFile)).toBe(0);
    expect(await memoryRowsFor(legacyFile)).toBe(0);
    expect(await bankChunkCount(legacyFile)).toBe(0);
    expect(await bankHasMarker(legacyMarker)).toBe(false);
  }, 180000);

  it('11. §7(8) activity-revival re-ingest — genuine touch after a forget re-ingests with fresh retention', async () => {
    // Documents the OD-4 trade: marker-stickiness was retired on purpose.
    const reScope = scopedSource(ttlSource!, 'reingest');
    const uniqueId = Date.now();
    const reMarker = `TTL-REINGEST-${uniqueId}`;
    const reFile = await writeScopedFile(
      reScope,
      'fading.md',
      `# Activity Revival ${uniqueId}\n\nMarker: ${reMarker}. Forgotten while old, genuinely touched after.`,
    );
    await ingestViaExplicitDoor(reScope);
    const firstRow = await prisma!.fileTracker.findFirst({ where: { filePath: reFile } });
    expect(firstRow).not.toBeNull();
    const firstCreatedAtMs = firstRow!.createdAt.getTime();

    // Age it out and let a real sweep forget it (only this row is past due).
    await ageFile(reFile, BACKDATE_DAYS);
    const sweep = await ttlService!.run();
    console.log(`[E2E-TtlSweep] §7(8) forget sweep: ${JSON.stringify(sweep)}`);
    expect(sweep.expired).toBe(1);
    expect(sweep.forgotten).toBe(1);
    expect(sweep.failed).toBe(0);
    expect(await trackerCountFor(reFile)).toBe(0);
    expect(await bankHasMarker(reMarker)).toBe(false);

    // A genuine touch re-arms eligibility by definition of the clock.
    touchFileNow(reFile);
    await runAndDrain(() => forceReprocessService!.resumeSource(SOURCE_ID, [reScope]));
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();

    // Full re-ingest with a FRESH retention period (new row, new createdAt).
    const reRow = await prisma!.fileTracker.findFirst({ where: { filePath: reFile } });
    expect(reRow).not.toBeNull();
    expect(reRow!.createdAt.getTime()).toBeGreaterThan(firstCreatedAtMs);
    expect(Date.now() - reRow!.createdAt.getTime()).toBeLessThan(120_000);
    expect(await memoryRowsFor(reFile)).toBeGreaterThan(0);
    expect(await bankHasMarker(reMarker)).toBe(true);
    expect(await bankChunkCount(reFile)).toBeGreaterThan(0);
  }, 240000);

  it('12. §7(9) non-TTL source — gate never entered, all pre-existing behavior unchanged', async () => {
    // The mirror of §7(5): the SAME aged fixture under a source WITHOUT
    // ttlDays (obsidian-style permanent material) is still batch-ingested —
    // the gate is strictly a per-source opt-in and is never entered here.
    const nonTtlScope = scopedSource(obsidianSource!, 'nonttl');
    const uniqueId = Date.now();
    const nonTtlMarker = `TTL-NONTTL-${uniqueId}`;
    const nonTtlFile = await writeScopedFile(
      nonTtlScope,
      'permanent-note.md',
      `# Permanent Material ${uniqueId}\n\nMarker: ${nonTtlMarker}. No ttlDays — never TTL-relevant.`,
    );
    await ageFile(nonTtlFile, BACKDATE_DAYS);
    expect(await trackerCountFor(nonTtlFile)).toBe(0);

    await runAndDrain(() => forceReprocessService!.resumeSource(OBSIDIAN_SOURCE_ID, [nonTtlScope]));
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();

    // Today's exact pre-existing behavior: an untracked file on a resume
    // enumeration is ingested — an aged mtime changed nothing. (The
    // contrast is §7(5): the identical age under a ttlDays source → zero.)
    // Config-wide non-TTL suites (obsidian-chunking et al.) pass unchanged.
    expect(await trackerCountFor(nonTtlFile)).toBe(1);
    expect(await memoryRowsFor(nonTtlFile)).toBeGreaterThan(0);
    expect(await bankChunkCount(nonTtlFile, nonTtlScope.memoryBank!)).toBeGreaterThan(0);
    expect(await bankHasMarker(nonTtlMarker, nonTtlScope.memoryBank!)).toBe(true);
  }, 240000);
});
