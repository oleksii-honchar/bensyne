/**
 * [E2E] Recover mode — spec §7 Phase 6.
 *
 * Proves the FULL recover flow end-to-end against the real pipeline:
 * bensyne Docker instance (started by global-setup), real Prisma/SQLite
 * tracker DB, and the real CLI entrypoint (src/main.ts) spawned as a
 * subprocess.
 *
 * Scenario (acceptance criteria):
 * 1. Ingest a file through the normal pipeline (ProcessFileUseCase) → tracked
 *    locally (FileTracker + FileMemoryTracker) and indexed in bensyne.
 *    An untracked file sits in the source directory (never ingested).
 * 2. Delete ONE chunk row from the bensyne file_metadata DB (simulating
 *    partial loss).
 * 3. Run `--recover` via the real CLI.
 * 4. Assert:
 *    - the missing chunk row is re-created on the bensyne side, and its memory
 *      is tracked in the local FileMemoryTracker;
 *    - the untracked file gained no file/chunk rows (no bensyne row, no
 *      local tracker);
 *    - the CLI process exits (code 0) after the pass.
 */

import { INestApplication } from '@nestjs/common';
import * as child_process from 'child_process';
import * as fs from 'fs/promises';
import { DatabaseSync } from 'node:sqlite';
import * as path from 'path';
import { promisify } from 'util';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { PrismaService } from '../../infrastructure/prisma/prisma.service';
import { FileMemoryTrackerRepository } from '../../infrastructure/repositories/file-memory-tracker.repository';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { ProcessFileUseCase } from '../../use-cases/process-file.use-case';
import { cleanupTempDir, createTempDir } from '../e2e-utils';
import { createTestApplication } from '../main.test-application';

const execAsync = promisify(child_process.exec);

const SOURCE_ID = 'e2e-test-source';
const MEMORY_BANK = 'e2e-test-ns';

// apps/racochu — walk up from src/e2e/recover-mode.
const RACOCHU_APP_DIR = path.resolve(__dirname, '..', '..', '..');
const RACOCHU_DB_PATH = path.join(RACOCHU_APP_DIR, 'data', 'racochu.db');

// Same compose project global-setup uses (env-setup/bensyne-docker-setup.ts).
const BENSYNE_COMPOSE_FILE = path.resolve(__dirname, '..', 'env-setup', 'docker-compose.bensyne.yml');
const BENSYNE_PROJECT = 'rag-e2e-bensyne';
const BENSYNE_URL = 'http://localhost:3001';

// Debounce(500ms) + chunking + MCP ingestion + Mnemosyne indexing.
const PROCESSING_WAIT_MS = 20000;
// Full CLI bootstrap (ts-node + prisma push + Nest init + recover pass).
const CLI_RUN_TIMEOUT_MS = 180000;

// A markdown doc long enough to produce multiple chunks. The effective chunk
// size for docs comes from `enhancement.maxCharacters.prose` (2000 in the e2e
// config), so this content is written to exceed 2000 chars per section and
// yield several chunks (guarantees a meaningful chunk-row deletion).
const TRACKED_CONTENT = (marker: string): string => `# Recover E2E Tracked File

Marker: ${marker}

## Section One

This section describes the first part of the recover test document. It contains enough prose to
form at least one semantic chunk on its own. The content must be long enough that the chunker
splits the document into several chunks so that deleting a single chunk row leaves the rest of
the file intact and verifiable.

The recover mode should only repair chunk-level gaps for files already tracked in the local
database. It computes the expected chunk set locally without enrichment, reads the stored set
from bensyne through a read-only MCP tool, and re-ingests only the missing chunks through the
regular pipeline. This first section repeats that idea several times so the markdown chunker
sees a substantial body of prose under the Section One heading rather than a tiny fragment.

Paragraph two of section one: verification also covers embedding existence. The read-only tool
reports, for every stored chunk, whether the referenced memory is still present. A chunk whose
memory is gone counts as damaged even if its row still exists. The repair path re-embeds such
chunks safely, guarded against the stale hash-index dedup trap.

Paragraph three of section one: the whole verification pass is CPU-only. No LLM call is made
while enumerating expected chunks, because the expected chunk set is computed with enrichment
explicitly skipped. Enrichment never rewrites chunk text, so the chunk hash stays identical
with or without it, which keeps the equality signal stable.

Paragraph four of section one: this paragraph adds more bulk to the section so the chunker has
no ambiguity about where the section boundary sits. A healthy file is skipped with zero repair
work, while a file with a missing chunk index or a missing memory is repaired by re-chunking
with enrichment applied as configured and submitting only the repair set.

## Section Two

This section describes the second part of the recover test document. It also contains enough
prose to form its own chunk. The chunk boundaries are deterministic: enrichment never rewrites
chunk text, so the expected chunk set computed by the recover verification path matches the
stored set produced at ingest time.

The repair set is submitted through the same ingest path used by the normal pipeline, with the
force-reembed flag enabled. When the dedup target memory is still alive, the normal dedup path
materializes the chunk row again with the existing memory id; when the memory is gone, the
stale hash-index entry and stale chunk rows are dropped first and the memory is re-embedded.

This section keeps the document above the chunk-size threshold on its own. Without enough prose
here the whole file could collapse into a single chunk, which would defeat the purpose of the
test. So this paragraph deliberately adds several sentences of recover-mode detail: only
database-tracked files are processed, untracked files are never touched, healthy chunks are
never re-submitted, and the whole pass runs to completion before the process exits.

## Section Three

This section provides additional bulk so the document reliably splits into multiple chunks. It
repeats recover-mode facts in different words: only database-tracked files are processed,
untracked files are never touched, and the process exits after the pass completes.

The expected chunk set maps every chunk index to the sha256 hash of its exact text. The stored
set comes from bensyne with the same index and hash values. A mismatch on either axis places
the chunk into the repair set. Everything else is left alone, which keeps the recovery pass
additive and cheap for healthy files.

Paragraph three of section three: the local FileMemoryTracker is updated as the repaired chunks
flow through the ingest use case, so the local database remains the source of truth for which
memories belong to which file even after a partial-loss event on the bensyne side.

## Section Four

This final section exists purely to push the document over multiple chunk boundaries. It
reiterates the acceptance criteria in yet more words so the markdown chunker reliably emits at
least three chunks for the file. Deleting one of those chunk rows simulates the partial loss
that the recover mode is designed to repair in a single pass.

When the recovery pass runs, it reads the file from disk, recomputes the expected chunk set
without enrichment, compares it against the stored chunk set, and submits only the chunks that
are missing or whose memory is gone. The queue drains before the CLI exits, and the exit code
is zero when the pass completes successfully.
`;

describe('[E2E] Recover mode — ingest → delete chunk row → CLI --recover → repair verified', () => {
  let app: INestApplication | null = null;
  let prisma: PrismaService | null = null;
  let processFileUseCase: ProcessFileUseCase | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let trackerRepo: FileMemoryTrackerRepository | null = null;
  let watchDir: string | undefined;
  let e2eDataDir: string | undefined;
  let tempDir: string | null = null;

  // Shared across sequential tests (maxWorkers: 1).
  let uniqueId: number;
  let marker: string;
  let trackedFilePath: string;
  let untrackedFilePath: string;
  let baselineChunkRows: { chunk_index: number; memory_id: string }[] = [];
  let fileId: string | undefined;
  let deletedChunkIndex: number | undefined;

  /** Writable handle on the bensyne bank file metadata DB (host volume). */
  function openBensyneDb(write = false): DatabaseSync {
    const dbPath = path.join(e2eDataDir!, 'banks', MEMORY_BANK, 'file_metadata.db');
    const db = write ? new DatabaseSync(dbPath) : new DatabaseSync(dbPath, { readOnly: true });
    if (write) {
      db.exec('PRAGMA busy_timeout = 5000');
    }
    return db;
  }

  /** Read-only handle on the racochu local tracker DB (Prisma 64-bit ids). */
  function openLocalDb(): DatabaseSync {
    return new DatabaseSync(RACOCHU_DB_PATH, { readOnly: true, readBigInts: true });
  }

  async function waitForBensyneHealth(maxAttempts = 60): Promise<void> {
    const checkInterval = 1000;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        const res = await fetch(`${BENSYNE_URL}/health`);
        if (res.ok) {
          return;
        }
      } catch {
        // not up yet
      }
      await new Promise(resolve => setTimeout(resolve, checkInterval));
    }
    throw new Error(`bensyne did not become healthy within ${maxAttempts * checkInterval}ms after restart`);
  }

  /**
   * The bensyne DB lives on a Docker bind mount. Writing to it from the host
   * while the container holds the file open desyncs the container's view
   * (observed: getFileChunks fails with "disk I/O error"). To simulate the
   * partial loss safely, stop the container first (no open handles), mutate the
   * SQLite file from the host, then start the container again and wait for it
   * to serve /health with the modified state.
   */
  async function mutateBensyneDbWithContainerStopped(mutate: (db: DatabaseSync) => void): Promise<void> {
    await execAsync(`docker compose -p ${BENSYNE_PROJECT} -f ${BENSYNE_COMPOSE_FILE} stop`, {
      timeout: 60000,
    });
    const db = openBensyneDb(true);
    try {
      mutate(db);
    } finally {
      db.close();
    }
    await execAsync(`docker compose -p ${BENSYNE_PROJECT} -f ${BENSYNE_COMPOSE_FILE} start`, {
      timeout: 60000,
    });
    await waitForBensyneHealth();
    console.log('[E2E-Recover] bensyne restarted with mutated DB');
  }

  function findBensyneFileId(db: DatabaseSync, filePath: string): string | undefined {
    const row = db.prepare('SELECT id FROM files WHERE path = ?').get(filePath) as { id: string } | undefined;
    return row?.id;
  }

  function getChunkRows(
    db: DatabaseSync,
    targetFileId: string,
  ): { chunk_index: number; memory_id: string }[] {
    const rows = db
      .prepare('SELECT chunk_index, memory_id FROM file_chunks WHERE file_id = ? ORDER BY chunk_index')
      .all(targetFileId) as { chunk_index: number; memory_id: string }[];
    return rows;
  }

  function findLocalTrackerId(db: DatabaseSync, filePath: string): bigint | undefined {
    // Prisma generates 64-bit big-endian ids — the local handle is opened with
    // readBigInts so node:sqlite returns them as bigint (also binds cleanly
    // into the follow-up query).
    const row = db.prepare('SELECT id FROM FileTracker WHERE filePath = ?').get(filePath) as
      { id: bigint } | undefined;
    return row?.id;
  }

  function getLocalMemoryIds(db: DatabaseSync, fileTrackerId: bigint): string[] {
    const rows = db
      .prepare('SELECT memoryId FROM FileMemoryTracker WHERE fileTrackerId = ?')
      .all(fileTrackerId) as { memoryId: string }[];
    return rows.map(r => r.memoryId);
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

    uniqueId = Date.now();
    marker = `RECOVER-E2E-${uniqueId}`;

    // The untracked file lives in the source directory BEFORE the app boots:
    // chokidar starts with ignoreInitial, so an existing file is never
    // ingested → it stays untracked for the whole scenario.
    untrackedFilePath = path.join(watchDir, `untracked-recover-${uniqueId}.md`);
    await fs.writeFile(untrackedFilePath, `# Untracked file ${uniqueId}\n\nNever processed.\n`, 'utf-8');

    // Ingestion temp dir (outside the watched dirs) so the file is processed
    // exactly once via ProcessFileUseCase, not by the watcher.
    tempDir = await createTempDir('rag-e2e-recover-');
    trackedFilePath = path.join(tempDir, `tracked-recover-${uniqueId}.md`);
    await fs.writeFile(trackedFilePath, TRACKED_CONTENT(marker), 'utf-8');

    app = await createTestApplication();
    await app.init();

    prisma = app.get(PrismaService);
    processFileUseCase = app.get(ProcessFileUseCase);
    processingQueue = app.get(FileProcessingQueue);
    trackerRepo = app.get(FileMemoryTrackerRepository);

    // Deterministic recover: clear trackers left by earlier suites for this
    // source so the recover pass only sees what THIS suite creates.
    await prisma!.fileTracker.deleteMany({ where: { sourceId: SOURCE_ID } });

    // Give FileWatcherService time to fully register watchers (ignoreInitial).
    await new Promise(resolve => setTimeout(resolve, 1000));
  }, 120000);

  afterAll(async () => {
    if (tempDir) {
      await cleanupTempDir(tempDir);
    }
    if (app) {
      const closePromise = app.close().catch(() => undefined);
      const timeoutPromise = new Promise(resolve => setTimeout(resolve, 30000));
      await Promise.race([closePromise, timeoutPromise]);
    }
  });

  it('1. baseline — tracked file ingested (tracker + bensyne chunks), untracked file untouched', async () => {
    const sources = app!.get(ConfigurationService).getWatchSources();
    const source = sources.find(s => s.id === SOURCE_ID);
    expect(source).toBeDefined();
    expect(source!.memoryBank).toBe(MEMORY_BANK);

    const result = await processFileUseCase!.execute({
      filePath: trackedFilePath,
      eventType: 'add',
      sourceId: SOURCE_ID,
      memoryBank: MEMORY_BANK,
      sourceConfig: source!,
    });
    expect(result.isOk()).toBe(true);

    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();

    // Local tracker: file is tracked with at least one memory mapping.
    const tracker = await trackerRepo!.findByFilePath(trackedFilePath);
    expect(tracker.isOk()).toBe(true);
    const tracked = tracker.getValue();
    expect(tracked).not.toBeNull();
    expect(tracked!.memoryIds.length).toBeGreaterThan(0);
    console.log(`[E2E-Recover] Tracked memory IDs: ${tracked!.memoryIds.length}`);

    // Bensyne side: file row indexed + at least 2 chunk rows (so deleting one
    // leaves the rest intact).
    const db = openBensyneDb();
    try {
      fileId = findBensyneFileId(db, trackedFilePath);
      expect(fileId).toBeDefined();
      baselineChunkRows = getChunkRows(db, fileId!);
      expect(baselineChunkRows.length).toBeGreaterThanOrEqual(2);
      console.log(`[E2E-Recover] Bensyne baseline chunk rows: ${baselineChunkRows.length}`);
    } finally {
      db.close();
    }

    // Untracked file: no bensyne row, no local tracker.
    const db2 = openBensyneDb();
    try {
      expect(findBensyneFileId(db2, untrackedFilePath)).toBeUndefined();
    } finally {
      db2.close();
    }
    const localDb = openLocalDb();
    try {
      expect(findLocalTrackerId(localDb, untrackedFilePath)).toBeUndefined();
    } finally {
      localDb.close();
    }
  }, 120000);

  it('2. partial loss — delete one chunk row in the bensyne DB', async () => {
    expect(fileId).toBeDefined();
    expect(baselineChunkRows.length).toBeGreaterThanOrEqual(2);

    // Delete the SECOND chunk row (index 1) — simulating partial loss.
    deletedChunkIndex = baselineChunkRows[1].chunk_index;
    await mutateBensyneDbWithContainerStopped(db => {
      const del = db
        .prepare('DELETE FROM file_chunks WHERE file_id = ? AND chunk_index = ?')
        .run(fileId!, deletedChunkIndex!);
      expect(Number(del.changes)).toBe(1);
    });

    const readDb = openBensyneDb();
    try {
      const remaining = getChunkRows(readDb, fileId!);
      expect(remaining.length).toBe(baselineChunkRows.length - 1);
      expect(remaining.some(c => c.chunk_index === deletedChunkIndex)).toBe(false);
      console.log(
        `[E2E-Recover] Deleted chunk_index=${deletedChunkIndex}; remaining rows=${remaining.length}`,
      );
    } finally {
      readDb.close();
    }
  }, 120000);

  it(
    '3. run the real CLI --recover and assert the process exits after the pass',
    async () => {
      // Release the app's SQLite connection before the CLI subprocess writes.
      if (app) {
        await app.close().catch(() => undefined);
        app = null;
      }

      const configPath = process.env.APP_CONFIG_PATH;
      expect(configPath).toBeDefined();

      const childEnv: NodeJS.ProcessEnv = { ...process.env };
      // Strip jest's ESM vm-modules flag — ts-node runs plain CJS here.
      delete childEnv.NODE_OPTIONS;

      const childArgs = [
        '-r',
        'ts-node/register',
        '-r',
        'tsconfig-paths/register',
        'src/main.ts',
        '--recover',
        '-s',
        SOURCE_ID,
      ];

      console.log(`[E2E-Recover] Spawning CLI: node ${childArgs.join(' ')} (cwd=${RACOCHU_APP_DIR})`);

      const { code, stdout, stderr } = await new Promise<{
        code: number | null;
        stdout: string;
        stderr: string;
      }>((resolve, reject) => {
        const child = child_process.spawn(process.execPath, childArgs, {
          cwd: RACOCHU_APP_DIR,
          env: childEnv,
          stdio: ['ignore', 'pipe', 'pipe'],
        });
        let out = '';
        let err = '';
        const timer = setTimeout(() => {
          child.kill('SIGKILL');
          reject(new Error(`racochu --recover did not exit within ${CLI_RUN_TIMEOUT_MS}ms`));
        }, CLI_RUN_TIMEOUT_MS);
        child.stdout.on('data', chunk => (out += chunk));
        child.stderr.on('data', chunk => (err += chunk));
        child.on('error', error => {
          clearTimeout(timer);
          reject(error);
        });
        child.on('close', code => {
          clearTimeout(timer);
          resolve({ code, stdout: out, stderr: err });
        });
      });

      console.log(`[E2E-Recover] CLI exit code: ${code}`);
      // Filtered dump for debugging: recover/repair/error lines from the real CLI.
      const interesting = stdout
        .split('\n')
        .filter(line => /recover|repair|Repair|Recover|error|ERROR|warn|Tracked files/i.test(line));
      if (interesting.length > 0) {
        console.log(`[E2E-Recover] CLI recover-relevant lines:\n${interesting.slice(-40).join('\n')}`);
      }
      if (stderr.length > 0) {
        console.log(`[E2E-Recover] CLI stderr tail:\n${stderr.split('\n').slice(-15).join('\n')}`);
      }

      // Behavioral exit proof: the process exits on its own after the pass.
      expect(code).toBe(0);
    },
    CLI_RUN_TIMEOUT_MS + 30000,
  );

  it('4. post-recover — chunk re-created + memory tracked, untracked file untouched', async () => {
    expect(fileId).toBeDefined();
    expect(deletedChunkIndex).toBeDefined();

    // Bensyne side: the deleted chunk row is back, total count restored.
    const db = openBensyneDb();
    let recreatedRow: { chunk_index: number; memory_id: string } | undefined;
    try {
      const rows = getChunkRows(db, fileId!);
      expect(rows.length).toBe(baselineChunkRows.length);
      recreatedRow = rows.find(c => c.chunk_index === deletedChunkIndex);
      expect(recreatedRow).toBeDefined();
      expect(recreatedRow!.memory_id.length).toBeGreaterThan(0);
      console.log(
        `[E2E-Recover] Recreated chunk_index=${deletedChunkIndex} memory_id=${recreatedRow!.memory_id}`,
      );
    } finally {
      db.close();
    }

    // Local tracker: the recreated chunk's memory is tracked for the file.
    const localDb = openLocalDb();
    try {
      const trackerId = findLocalTrackerId(localDb, trackedFilePath);
      expect(trackerId).toBeDefined();
      const memoryIds = getLocalMemoryIds(localDb, trackerId!);
      expect(memoryIds).toContain(recreatedRow!.memory_id);
      console.log(`[E2E-Recover] Local tracker memory IDs: ${memoryIds.length}`);
    } finally {
      localDb.close();
    }

    // Untracked file: still no bensyne row and no local tracker — recover
    // only iterates DB-tracked files.
    const db2 = openBensyneDb();
    try {
      expect(findBensyneFileId(db2, untrackedFilePath)).toBeUndefined();
    } finally {
      db2.close();
    }
    const localDb2 = openLocalDb();
    try {
      expect(findLocalTrackerId(localDb2, untrackedFilePath)).toBeUndefined();
    } finally {
      localDb2.close();
    }
  }, 60000);
});
