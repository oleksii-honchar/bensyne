import { FileMemoryTracker } from '@/domain/file-memory-tracker.aggregate';
import { FileTracker } from '@/domain/file-tracker.aggregate';
import { generateId } from '@/utils/big-endian-id';
import { Test, TestingModule } from '@nestjs/testing';
import { PrismaService } from '../prisma/prisma.service';
import { FileTrackerRepository } from './file-tracker.repository';
import {
  aMockPrismaFileMemoryTracker,
  aMockPrismaFileTracker,
  aPrismaFileTracker,
} from './file-tracker.repository.test-utils';

describe('FileTrackerRepository', () => {
  let repository: FileTrackerRepository;
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
      providers: [FileTrackerRepository, { provide: PrismaService, useValue: mockPrisma }],
    }).compile();

    repository = module.get<FileTrackerRepository>(FileTrackerRepository);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('findOrCreate', () => {
    it('returns existing tracker when found by filePath', async () => {
      const existing = aPrismaFileTracker({
        id: 1001n,
        filePath: '/test/file.txt',
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      });

      prismaFileTracker.findUnique.mockResolvedValue(existing);

      const fileTracker = FileTracker.of({ filePath: '/test/file.txt' }).getValue().add().getValue();
      const result = await repository.findOrCreate(fileTracker, 'source-001', 'vault-knowledge');

      expect(result.isOk()).toBe(true);
      expect(prismaFileTracker.findUnique).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
        include: { memories: true },
      });
      expect(prismaFileTracker.upsert).not.toHaveBeenCalled();
    });

    it('creates new tracker when not found', async () => {
      const upsertResult = aPrismaFileTracker({
        id: 1002n,
        filePath: '/test/new-file.txt',
        sourceId: 'source-002',
        memoryBank: 'default',
      });

      // First call: findUnique by filePath (not found)
      // Second call: findUnique by id in syncMemories (returns upsert result)
      prismaFileTracker.findUnique.mockResolvedValueOnce(null).mockResolvedValueOnce(upsertResult);
      prismaFileTracker.upsert.mockResolvedValue(upsertResult);

      const fileTracker = FileTracker.of({ filePath: '/test/new-file.txt' }).getValue().add().getValue();
      const result = await repository.findOrCreate(fileTracker, 'source-002', 'default');

      expect(result.isOk()).toBe(true);
      expect(prismaFileTracker.upsert).toHaveBeenCalledWith(
        expect.objectContaining({
          where: { filePath: '/test/new-file.txt' },
          create: expect.objectContaining({
            filePath: '/test/new-file.txt',
            sourceId: 'source-002',
            memoryBank: 'default',
          }),
        }),
      );
    });

    it('syncs memory associations when creating with existing memories', async () => {
      const upsertResult = aPrismaFileTracker({
        id: 1003n,
        filePath: '/test/with-memories.txt',
        sourceId: 'source-003',
        memoryBank: 'default',
        memories: [{ id: 2001n, memoryId: 'mem-001', fileTrackerId: 1003n }],
      });

      // First call: findUnique by filePath (not found)
      // Second call: findUnique by id in syncMemories (returns upsert result with existing memories)
      prismaFileTracker.findUnique.mockResolvedValueOnce(null).mockResolvedValueOnce(upsertResult);
      prismaFileTracker.upsert.mockResolvedValue(upsertResult);
      prismaFileMemoryTracker.create.mockResolvedValue({
        id: 2002n,
        memoryId: 'mem-002',
        fileTrackerId: 1003n,
        createdAt: new Date(),
      });

      const fileTracker = FileTracker.of({ filePath: '/test/with-memories.txt' }).getValue().add().getValue();
      const result = await repository.findOrCreate(fileTracker, 'source-003', 'default', [
        'mem-001',
        'mem-002',
      ]);

      expect(result.isOk()).toBe(true);
      // mem-001 already exists, mem-002 should be created
      expect(prismaFileMemoryTracker.create).toHaveBeenCalledWith({
        data: expect.objectContaining({
          fileTrackerId: 1003n,
          memoryId: 'mem-002',
        }),
      });
    });
  });

  describe('deleteByFilePath', () => {
    it('deletes FileTracker record (cascade deletes memories)', async () => {
      prismaFileTracker.delete.mockResolvedValue(
        aPrismaFileTracker({
          id: 1001n,
          filePath: '/test/file.txt',
          sourceId: 'source-001',
          memoryBank: 'vault-knowledge',
        }),
      );

      const result = await repository.deleteByFilePath('/test/file.txt');

      expect(result.isOk()).toBe(true);
      expect(prismaFileTracker.delete).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
      });
    });

    it('returns ok when record does not exist (swallows P2025)', async () => {
      const error = new Error('Record to delete does not exist.');
      (error as { code?: string }).code = 'P2025';

      prismaFileTracker.delete.mockRejectedValue(error);

      const result = await repository.deleteByFilePath('/nonexistent/file.txt');

      expect(result.isOk()).toBe(true);
      expect(prismaFileTracker.delete).toHaveBeenCalledWith({
        where: { filePath: '/nonexistent/file.txt' },
      });
    });

    it('returns ko on unexpected error', async () => {
      const error = new Error('Database connection error');
      prismaFileTracker.delete.mockRejectedValue(error);

      const result = await repository.deleteByFilePath('/test/file.txt');

      expect(result.isOk()).toBe(false);
      expect(result.getErrors()).toHaveLength(1);
    });
  });

  describe('persist', () => {
    it('upserts file tracker and returns result', async () => {
      const upsertResult = aPrismaFileTracker({
        id: 1001n,
        filePath: '/test/file.txt',
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      });
      prismaFileTracker.upsert.mockResolvedValue(upsertResult);
      // syncMemories calls findUnique by id
      prismaFileTracker.findUnique.mockResolvedValue(upsertResult);

      const fileMemoryTracker = FileMemoryTracker.of({
        id: generateId(),
        filePath: '/test/file.txt',
        memoryIds: ['mem-001'],
        sourceId: 'source-001',
        memoryBank: 'vault-knowledge',
      }).getValue();
      const result = await repository.persist(fileMemoryTracker);

      expect(result.isOk()).toBe(true);
      expect(prismaFileTracker.upsert).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
        create: {
          id: fileMemoryTracker.id,
          filePath: '/test/file.txt',
          sourceId: 'source-001',
          memoryBank: 'vault-knowledge',
        },
        update: {
          sourceId: 'source-001',
          memoryBank: 'vault-knowledge',
        },
        include: { memories: true },
      });
    });

    it('syncs memories: adds new and removes deleted', async () => {
      const upsertResult = aPrismaFileTracker({
        id: 1002n,
        filePath: '/test/sync.txt',
        sourceId: 'source-002',
        memoryBank: 'default',
        memories: [
          { id: 2001n, memoryId: 'mem-001', fileTrackerId: 1002n },
          { id: 2002n, memoryId: 'mem-003', fileTrackerId: 1002n },
        ],
      });
      prismaFileTracker.upsert.mockResolvedValue(upsertResult);
      // syncMemories calls findUnique by id — returns DB state with existing memories
      prismaFileTracker.findUnique.mockResolvedValue(upsertResult);
      prismaFileMemoryTracker.create.mockResolvedValue({
        id: 2003n,
        memoryId: 'mem-002',
        fileTrackerId: 1002n,
        createdAt: new Date(),
      });

      const fileMemoryTracker = FileMemoryTracker.of({
        id: generateId(),
        filePath: '/test/sync.txt',
        memoryIds: ['mem-001', 'mem-002'],
        sourceId: 'source-002',
        memoryBank: 'default',
      }).getValue();
      const result = await repository.persist(fileMemoryTracker);

      expect(result.isOk()).toBe(true);
      // mem-003 was in DB but not in aggregate -> should be deleted
      expect(prismaFileMemoryTracker.deleteMany).toHaveBeenCalledWith({
        where: { fileTrackerId: 1002n, memoryId: 'mem-003' },
      });
      // mem-002 was in aggregate but not in DB -> should be created
      expect(prismaFileMemoryTracker.create).toHaveBeenCalledWith({
        data: expect.objectContaining({
          fileTrackerId: 1002n,
          memoryId: 'mem-002',
        }),
      });
    });

    it('does nothing when memories are already in sync', async () => {
      const upsertResult = aPrismaFileTracker({
        id: 1003n,
        filePath: '/test/in-sync.txt',
        sourceId: 'source-003',
        memoryBank: 'default',
        memories: [{ id: 2001n, memoryId: 'mem-001', fileTrackerId: 1003n }],
      });
      prismaFileTracker.upsert.mockResolvedValue(upsertResult);
      // syncMemories calls findUnique by id — returns same memories as aggregate
      prismaFileTracker.findUnique.mockResolvedValue(upsertResult);

      const fileMemoryTracker = FileMemoryTracker.of({
        id: generateId(),
        filePath: '/test/in-sync.txt',
        memoryIds: ['mem-001'],
        sourceId: 'source-003',
        memoryBank: 'default',
      }).getValue();
      const result = await repository.persist(fileMemoryTracker);

      expect(result.isOk()).toBe(true);
      expect(prismaFileMemoryTracker.deleteMany).not.toHaveBeenCalled();
      expect(prismaFileMemoryTracker.create).not.toHaveBeenCalled();
    });
  });
});
