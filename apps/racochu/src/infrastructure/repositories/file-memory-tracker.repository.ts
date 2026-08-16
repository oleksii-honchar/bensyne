import { FileMemoryTracker } from '@/domain/file-memory-tracker.aggregate';
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
   */
  async updateFileTrackerHash(
    filePath: string,
    fileHash: string | undefined,
    hardwareId: string | undefined,
  ): Promise<void> {
    const updateData: { fileHash?: string | null; hardwareId?: string | null } = {};
    if (fileHash !== undefined) {
      updateData.fileHash = fileHash ?? null;
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
