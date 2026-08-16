import { Test, TestingModule } from '@nestjs/testing';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { FileMemoryTrackerRepository } from './file-memory-tracker.repository';
import {
  aFileMemoryTracker,
  aPrismaFileMemoryTracker,
  aPrismaFileMemoryTrackerMemory,
} from './file-memory-tracker.repository.test-utils';
import { aMockPrismaFileMemoryTracker, aMockPrismaFileTracker } from './file-tracker.repository.test-utils';

describe('FileMemoryTrackerRepository', () => {
  let repository: FileMemoryTrackerRepository;
  let prismaFileTracker: ReturnType<typeof aMockPrismaFileTracker>;
  let prismaFileMemoryTracker: ReturnType<typeof aMockPrismaFileMemoryTracker>;

  beforeEach(async () => {
    prismaFileTracker = aMockPrismaFileTracker();
    prismaFileMemoryTracker = aMockPrismaFileMemoryTracker();

    const mockPrisma = {
      fileTracker: prismaFileTracker,
      fileMemoryTracker: prismaFileMemoryTracker,
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [FileMemoryTrackerRepository, { provide: PrismaService, useValue: mockPrisma }],
    }).compile();

    repository = module.get<FileMemoryTrackerRepository>(FileMemoryTrackerRepository);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('findByFilePath', () => {
    it('returns tracker when record exists with memories', async () => {
      const tracker = aFileMemoryTracker({
        filePath: '/test/file.txt',
        memoryIds: ['mem-001'],
      });
      const trackerJson = tracker.toJson();
      const prismaRecord = aPrismaFileMemoryTracker({
        id: trackerJson.id,
        filePath: trackerJson.filePath,
        sourceId: trackerJson.sourceId,
        memoryBank: trackerJson.memoryBank,
        memories: [
          aPrismaFileMemoryTrackerMemory({ id: 9001n, memoryId: 'mem-001', fileTrackerId: tracker.id }),
          aPrismaFileMemoryTrackerMemory({ id: 9002n, memoryId: 'mem-002', fileTrackerId: tracker.id }),
        ],
      });

      prismaFileTracker.findUnique.mockResolvedValue(prismaRecord);

      const result = await repository.getMemoryIds('/test/file.txt');

      expect(result).toEqual(['mem-001', 'mem-002']);
    });

    it('returns empty array when no tracker found', async () => {
      prismaFileTracker.findUnique.mockResolvedValue(null);

      const result = await repository.getMemoryIds('/nonexistent/file.txt');

      expect(result).toEqual([]);
    });

    it('returns empty array when tracker has no memories', async () => {
      const tracker = aFileMemoryTracker({ filePath: '/test/file.txt', memoryIds: [] });
      const trackerJson = tracker.toJson();
      const prismaRecord = aPrismaFileMemoryTracker({
        id: trackerJson.id,
        filePath: trackerJson.filePath,
        sourceId: trackerJson.sourceId,
        memoryBank: trackerJson.memoryBank,
        memories: [],
      });

      prismaFileTracker.findUnique.mockResolvedValue(prismaRecord);

      const result = await repository.getMemoryIds('/test/file.txt');

      expect(result).toEqual([]);
    });
  });

  describe('deleteByFilePath', () => {
    it('deletes FileTracker record (cascade deletes memories)', async () => {
      prismaFileTracker.delete.mockResolvedValue(
        aPrismaFileMemoryTracker({
          id: 1001n,
          filePath: '/test/file.txt',
          sourceId: 'source-001',
          memoryBank: 'vault-knowledge',
          createdAt: new Date(),
          updatedAt: new Date(),
        }),
      );

      await repository.deleteByFilePath('/test/file.txt');

      expect(prismaFileTracker.delete).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
      });
    });

    it('swallows Prisma RecordNotFoundError when record does not exist', async () => {
      const error = new Error('Record to delete does not exist.');
      (error as Prisma.PrismaClientKnownRequestError).code = 'P2025';

      prismaFileTracker.delete.mockRejectedValue(error);

      await expect(repository.deleteByFilePath('/nonexistent/file.txt')).resolves.not.toThrow();
      expect(prismaFileTracker.delete).toHaveBeenCalledWith({
        where: { filePath: '/nonexistent/file.txt' },
      });
    });
  });

  describe('updateFileTrackerHash', () => {
    it('updates both fileHash and hardwareId when both provided', async () => {
      prismaFileTracker.updateMany.mockResolvedValue({ count: 1 });

      await repository.updateFileTrackerHash('/test/file.txt', 'sha256-abc', 'hw-123');

      expect(prismaFileTracker.updateMany).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
        data: { fileHash: 'sha256-abc', hardwareId: 'hw-123' },
      });
    });

    it('updates only fileHash when hardwareId is undefined', async () => {
      prismaFileTracker.updateMany.mockResolvedValue({ count: 1 });

      await repository.updateFileTrackerHash('/test/file.txt', 'sha256-abc', undefined);

      expect(prismaFileTracker.updateMany).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
        data: { fileHash: 'sha256-abc' },
      });
    });

    it('updates only hardwareId when fileHash is undefined', async () => {
      prismaFileTracker.updateMany.mockResolvedValue({ count: 1 });

      await repository.updateFileTrackerHash('/test/file.txt', undefined, 'hw-123');

      expect(prismaFileTracker.updateMany).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
        data: { hardwareId: 'hw-123' },
      });
    });

    it('passes empty string as-is when fileHash is empty string', async () => {
      prismaFileTracker.updateMany.mockResolvedValue({ count: 1 });

      await repository.updateFileTrackerHash('/test/file.txt', '', 'hw-123');

      expect(prismaFileTracker.updateMany).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
        data: { fileHash: '', hardwareId: 'hw-123' },
      });
    });
  });
});
