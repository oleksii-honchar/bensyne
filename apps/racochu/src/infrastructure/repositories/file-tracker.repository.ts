import { FileMemoryTracker } from '@/domain/file-memory-tracker.aggregate';
import { FileTracker } from '@/domain/file-tracker.aggregate';
import { generateId } from '@/utils/big-endian-id';
import { ErrorWithDetails } from '@/utils/error-with-details';
import { Result } from '@/utils/result';
import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

@Injectable()
export class FileTrackerRepository {
  constructor(private readonly prisma: PrismaService) {}

  /**
   * Find existing tracker by filePath, or create a new one via Prisma upsert.
   * Optionally syncs memory associations if memoryIds are provided.
   */
  async findOrCreate(
    tracker: FileTracker,
    sourceId: string,
    memoryBank: string,
    memoryIds: string[] = [],
  ): Promise<Result<FileTracker>> {
    const existing = await this.prisma.fileTracker.findUnique({
      where: { filePath: tracker.filePath },
      include: { memories: true },
    });

    if (existing) {
      return Result.ok(tracker);
    }

    const saved = await this.prisma.fileTracker.upsert({
      where: { filePath: tracker.filePath },
      create: {
        id: generateId(),
        filePath: tracker.filePath,
        sourceId,
        memoryBank,
      },
      update: {
        sourceId,
        memoryBank,
      },
      include: { memories: true },
    });

    // Sync memory associations if provided
    if (memoryIds.length > 0) {
      await this.syncMemories(saved.id, memoryIds);
    }

    return Result.ok(tracker);
  }

  /**
   * Delete FileTracker by filePath. Cascade deletes FileMemoryTracker memories.
   * Swallows Prisma RecordNotFoundError (P2025) — idempotent delete.
   */
  async deleteByFilePath(filePath: string): Promise<Result<void>> {
    try {
      await this.prisma.fileTracker.delete({
        where: { filePath },
      });
      return Result.ok(undefined);
    } catch (error: unknown) {
      const prismaError = error as { code?: string };
      if (prismaError.code === 'P2025') {
        return Result.ok(undefined);
      }
      return Result.ko([
        new ErrorWithDetails(
          `Failed to delete FileTracker: ${filePath}. ${(error as Error).message}`,
          'DeleteFileTrackerError',
        ),
      ]);
    }
  }

  /**
   * Upsert a FileMemoryTracker aggregate to the database.
   * Persists file-level data and syncs memory associations via FileMemoryTracker.
   * This is the current FileMemoryTrackerRepository.upsert logic moved here.
   */
  async persist(tracker: FileMemoryTracker): Promise<Result<FileMemoryTracker>> {
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
    await this.syncMemories(saved.id, tracker.memoryIds);

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
   * Sync memory associations for a file tracker.
   * Adds new memories and removes deleted ones based on the provided memoryIds.
   */
  private async syncMemories(fileTrackerId: bigint, memoryIds: string[]): Promise<void> {
    const existing = await this.prisma.fileTracker.findUnique({
      where: { id: fileTrackerId },
      include: { memories: true },
    });

    if (!existing) {
      return;
    }

    const existingMemoryIds = new Set(existing.memories.map((m: { memoryId: string }) => m.memoryId));
    const trackerMemoryIds = new Set(memoryIds);

    // Remove memories that are no longer in the aggregate
    for (const memId of existingMemoryIds) {
      if (!trackerMemoryIds.has(memId)) {
        await this.prisma.fileMemoryTracker.deleteMany({
          where: { fileTrackerId, memoryId: memId },
        });
      }
    }

    // Add new memories
    for (const memId of trackerMemoryIds) {
      if (!existingMemoryIds.has(memId)) {
        await this.prisma.fileMemoryTracker.create({
          data: { id: generateId(), fileTrackerId, memoryId: memId },
        });
      }
    }
  }
}
