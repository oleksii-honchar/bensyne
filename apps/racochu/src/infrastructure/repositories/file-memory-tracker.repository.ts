import { FileMemoryTracker } from '@/domain/file-memory-tracker.aggregate';
import { FileTrackerSkipReason } from '@/domain/file-tracker.aggregate';
import { generateId } from '@/utils/big-endian-id';
import { ErrorWithDetails } from '@/utils/error-with-details';
import { Result } from '@/utils/result';
import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

@Injectable()
export class FileMemoryTrackerRepository {
  constructor(private readonly prisma: PrismaService) {}

  async findByFilePath(filePath: string): Promise<Result<FileMemoryTracker | null>> {
    const tracker = await this.prisma.fileTracker.findUnique({
      where: { filePath },
      include: { memories: true },
    });

    if (!tracker) {
      return Result.ko([new ErrorWithDetails(`Can't find tracker; filePath=${filePath}`)]);
    }

    const memoryIds = tracker.memories.map((m: { memoryId: string }) => m.memoryId);

    const result = FileMemoryTracker.of({
      id: tracker.id,
      filePath: tracker.filePath,
      memoryIds,
      sourceId: tracker.sourceId,
      memoryBank: tracker.memoryBank,
    });

    return result.isOk()
      ? result
      : Result.ko([new ErrorWithDetails('Invalid FileMemoryTracker', 'InvalidFileMemoryTracker')]);
  }

  /**
   * Find all tracked files for a given sourceId, each mapped to a FileMemoryTracker
   * aggregate. Used by reconciliation to iterate over every file tracked for a source.
   *
   * Empty result is Result.ok([]). Malformed rows (that fail aggregate construction)
   * are skipped so a single bad record never blocks reconciliation of the rest;
   * Prisma-level errors still propagate.
   */
  async findBySourceId(sourceId: string): Promise<Result<FileMemoryTracker[]>> {
    const trackers = await this.prisma.fileTracker.findMany({
      where: { sourceId },
      include: { memories: true },
    });

    if (trackers.length === 0) {
      return Result.ok([]);
    }

    const aggregates: FileMemoryTracker[] = [];
    for (const tracker of trackers) {
      const memoryIds = tracker.memories.map((m: { memoryId: string }) => m.memoryId);

      const result = FileMemoryTracker.of({
        id: tracker.id,
        filePath: tracker.filePath,
        memoryIds,
        sourceId: tracker.sourceId,
        memoryBank: tracker.memoryBank,
      });

      if (result.isKo()) {
        continue;
      }

      aggregates.push(result.getValue());
    }

    return Result.ok(aggregates);
  }

  /**
   * Find all tracked files for a given sourceId whose createdAt is strictly before
   * the cutoff date. The age filter lives in SQL (createdAt lt cutoff); the
   * FileMemoryTracker aggregate stays timestamp-free.
   *
   * Empty result is Result.ok([]). Malformed rows (that fail aggregate construction)
   * are skipped so a single bad record never blocks the rest;
   * Prisma-level errors still propagate.
   */
  // Deprecated: activity-clock derivation (ADR-8/ADR-9) replaced the createdAt SQL age clock;
  // kept for API compatibility — remove in a future cleanup.
  async findExpiredBySourceId(sourceId: string, cutoff: Date): Promise<Result<FileMemoryTracker[]>> {
    const trackers = await this.prisma.fileTracker.findMany({
      where: { sourceId, createdAt: { lt: cutoff } },
      include: { memories: true },
    });

    if (trackers.length === 0) {
      return Result.ok([]);
    }

    const aggregates: FileMemoryTracker[] = [];
    for (const tracker of trackers) {
      const memoryIds = tracker.memories.map((m: { memoryId: string }) => m.memoryId);

      const result = FileMemoryTracker.of({
        id: tracker.id,
        filePath: tracker.filePath,
        memoryIds,
        sourceId: tracker.sourceId,
        memoryBank: tracker.memoryBank,
      });

      if (result.isKo()) {
        continue;
      }

      aggregates.push(result.getValue());
    }

    return Result.ok(aggregates);
  }

  /**
   * Find the createdAt timestamp for a tracker by filePath, used to re-verify
   * TTL expiry immediately before forgetting. The FileMemoryTracker aggregate
   * stays timestamp-free; only the raw createdAt is returned here.
   *
   * Returns Result.ok(null) when no tracker exists for the filePath.
   */
  async findCreatedAtByFilePath(filePath: string): Promise<Result<Date | null>> {
    const tracker = await this.prisma.fileTracker.findUnique({
      where: { filePath },
      select: { createdAt: true },
    });

    return Result.ok(tracker ? tracker.createdAt : null);
  }

  /**
   * Read only the ingest-gate columns (fileHash, skipReason) for a filePath —
   * the single indexed read used by the hash-gate. Result.ok(null) means the
   * file is untracked (no FileTracker row). Unlike the methods above that let
   * Prisma errors propagate, a read failure is converted to Result.ko so the
   * gate caller can decide degradation (fail-open) at its own boundary.
   */
  async findHashAndSkipReasonByFilePath(
    filePath: string,
  ): Promise<Result<{ fileHash: string | null; skipReason: string | null } | null>> {
    try {
      const row = await this.prisma.fileTracker.findUnique({
        where: { filePath },
        select: { fileHash: true, skipReason: true },
      });

      if (!row) {
        return Result.ok(null);
      }

      return Result.ok({ fileHash: row.fileHash, skipReason: row.skipReason });
    } catch (error: unknown) {
      return Result.ko([
        new ErrorWithDetails(
          `Failed to read gate state for FileTracker: ${filePath}. ${(error as Error).message}`,
          'ReadFileTrackerGateStateError',
        ),
      ]);
    }
  }

  /**
   * Find existing tracker by filePath, or save the provided aggregate with a pre-generated ID.
   * Aggregate-first: caller creates the aggregate with domain logic, repository just persists it.
   */
  async findOrCreate(tracker: FileMemoryTracker): Promise<Result<FileMemoryTracker>> {
    const existing = await this.findByFilePath(tracker.filePath);
    if (existing.isOk() && existing.getValue()) {
      return existing as Result<FileMemoryTracker>;
    }

    return await this.upsert(tracker);
  }

  /**
   * Save (upsert) a FileMemoryTracker aggregate to the database.
   * Infrastructure term — just persists the aggregate as-is.
   */
  async upsert(tracker: FileMemoryTracker): Promise<Result<FileMemoryTracker>> {
    const saved = await this.prisma.fileTracker.upsert({
      where: { filePath: tracker.filePath },
      create: {
        id: tracker.id,
        filePath: tracker.filePath,
        sourceId: tracker.sourceId,
        memoryBank: tracker.memoryBank,
      },
      update: {
        sourceId: tracker.sourceId,
        memoryBank: tracker.memoryBank,
      },
      include: { memories: true },
    });

    // Sync memories: add new ones, remove deleted ones
    const existingMemoryIds = new Set(saved.memories.map((m: { memoryId: string }) => m.memoryId));
    const trackerMemoryIds = new Set(tracker.memoryIds);

    // Remove memories that are no longer in the aggregate
    for (const memId of existingMemoryIds) {
      if (!trackerMemoryIds.has(memId)) {
        await this.prisma.fileMemoryTracker.deleteMany({
          where: { fileTrackerId: saved.id, memoryId: memId },
        });
      }
    }

    // Add new memories
    for (const memId of trackerMemoryIds) {
      if (!existingMemoryIds.has(memId)) {
        await this.prisma.fileMemoryTracker.create({
          data: { id: generateId(), fileTrackerId: saved.id, memoryId: memId },
        });
      }
    }

    const result = FileMemoryTracker.of({
      id: saved.id,
      filePath: saved.filePath,
      memoryIds: tracker.memoryIds,
      sourceId: saved.sourceId,
      memoryBank: saved.memoryBank,
    });

    return result;
  }

  /**
   * Record a terminal-skip decision on the FileTracker row keyed by filePath.
   * Create path uses the same application-generated id as every other FileTracker
   * write in this file (generateId()); update path refreshes fileHash,
   * hardwareId and skipReason only — identity columns stay untouched.
   *
   * Never touches FileMemoryTracker rows: a terminal skip is a decision with
   * zero memories by definition (spec C1 invariant). A Prisma failure is
   * converted to Result.ko (same conversion style as deleteByFilePath above) —
   * recording is non-fatal and the caller decides how to degrade.
   *
   * Callers must provide fileHash: a skip row without a hash cannot be
   * re-evaluated by the gate and breaks the "row ⇒ final decision on these
   * exact bytes" invariant (enforced at the use-case layer).
   */
  async upsertTerminalSkip(
    filePath: string,
    sourceId: string,
    memoryBank: string,
    fileHash: string | null,
    hardwareId: string | null,
    skipReason: FileTrackerSkipReason,
  ): Promise<Result<void>> {
    try {
      await this.prisma.fileTracker.upsert({
        where: { filePath },
        create: {
          id: generateId(),
          filePath,
          sourceId,
          memoryBank,
          fileHash,
          hardwareId,
          skipReason,
        },
        update: {
          fileHash,
          hardwareId,
          skipReason,
        },
      });

      return Result.ok(undefined);
    } catch (error: unknown) {
      return Result.ko([
        new ErrorWithDetails(
          `Failed to upsert terminal skip for FileTracker: ${filePath}. ${(error as Error).message}`,
          'UpsertTerminalSkipError',
        ),
      ]);
    }
  }

  async getMemoryIds(filePath: string): Promise<string[]> {
    const tracker = await this.prisma.fileTracker.findUnique({
      where: { filePath },
      include: { memories: true },
    });

    if (!tracker) {
      return [];
    }

    return tracker.memories.map((m: { memoryId: string }) => m.memoryId);
  }

  /**
   * Update fileHash and/or hardwareId on the FileTracker parent record.
   * Only sets fields that are provided (non-undefined).
   *
   * A hash write ALWAYS clears skipReason (spec C3 step 5): a row reaching
   * this path via trackMemory belongs to content that passed every
   * terminal-skip branch, so any recorded skip is stale for these bytes.
   * Clearing null rows keeps them null — no new behavior for plain rows.
   */
  async updateFileTrackerHash(
    filePath: string,
    fileHash: string | undefined,
    hardwareId: string | undefined,
  ): Promise<void> {
    const updateData: { fileHash?: string | null; hardwareId?: string | null; skipReason?: null } = {};
    if (fileHash !== undefined) {
      updateData.fileHash = fileHash ?? null;
      updateData.skipReason = null;
    }
    if (hardwareId !== undefined) {
      updateData.hardwareId = hardwareId ?? null;
    }

    await this.prisma.fileTracker.updateMany({
      where: { filePath },
      data: updateData,
    });
  }

  /**
   * Delete tracker by filePath (cascade deletes memories).
   */
  async deleteByFilePath(filePath: string): Promise<void> {
    try {
      await this.prisma.fileTracker.delete({
        where: { filePath },
      });
    } catch (error: unknown) {
      const prismaError = error as { code?: string };
      if (prismaError.code !== 'P2025') {
        throw error;
      }
    }
  }
}
