import { Test, TestingModule } from '@nestjs/testing';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { FileMemoryTrackerRepository } from './file-memory-tracker.repository';
import {
  aFileMemoryTracker,
  aFileTrackerTableFake,
  aPrismaFileMemoryTracker,
  aPrismaFileMemoryTrackerMemory,
  PrismaFileMemoryTrackerRecord,
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

  describe('findBySourceId', () => {
    it('returns all trackers for the given sourceId with their memories', async () => {
      const sourceId = 'src-1';
      const filePath1 = '/test/file-1.txt';
      const filePath2 = '/test/file-2.txt';
      const id1 = aFileMemoryTracker({ filePath: filePath1 }).toJson().id;
      const id2 = aFileMemoryTracker({ filePath: filePath2 }).toJson().id;

      prismaFileTracker.findMany.mockResolvedValue([
        aPrismaFileMemoryTracker({
          id: id1,
          filePath: filePath1,
          sourceId,
          memoryBank: 'bank-a',
          memories: [
            aPrismaFileMemoryTrackerMemory({ id: 9101n, memoryId: 'mem-001', fileTrackerId: id1 }),
            aPrismaFileMemoryTrackerMemory({ id: 9102n, memoryId: 'mem-002', fileTrackerId: id1 }),
          ],
        }),
        aPrismaFileMemoryTracker({
          id: id2,
          filePath: filePath2,
          sourceId,
          memoryBank: 'bank-b',
          memories: [aPrismaFileMemoryTrackerMemory({ id: 9103n, memoryId: 'mem-003', fileTrackerId: id2 })],
        }),
      ]);

      const result = await repository.findBySourceId(sourceId);

      expect(prismaFileTracker.findMany).toHaveBeenCalledWith({
        where: { sourceId },
        include: { memories: true },
      });
      expect(result.isOk()).toBe(true);
      const trackers = result.getValue();
      expect(trackers).toHaveLength(2);
      expect(trackers.map(t => t.filePath)).toEqual([filePath1, filePath2]);
      expect(trackers[0].memoryIds).toEqual(['mem-001', 'mem-002']);
      expect(trackers[1].memoryIds).toEqual(['mem-003']);
    });

    it('returns Result.ok([]) when no trackers exist for the source', async () => {
      prismaFileTracker.findMany.mockResolvedValue([]);

      const result = await repository.findBySourceId('no-such-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual([]);
    });

    it('skips malformed rows and returns only valid trackers', async () => {
      const sourceId = 'src-1';
      const validFilePath = '/test/valid.txt';
      const validId = aFileMemoryTracker({ filePath: validFilePath }).toJson().id;

      prismaFileTracker.findMany.mockResolvedValue([
        aPrismaFileMemoryTracker({
          id: validId,
          filePath: validFilePath,
          sourceId,
          memoryBank: 'bank-a',
          memories: [
            aPrismaFileMemoryTrackerMemory({ id: 9104n, memoryId: 'mem-001', fileTrackerId: validId }),
          ],
        }),
        // Malformed: empty filePath fails the aggregate schema.
        aPrismaFileMemoryTracker({
          id: aFileMemoryTracker().toJson().id,
          filePath: '',
          sourceId,
          memoryBank: 'bank-a',
          memories: [],
        }),
      ]);

      const result = await repository.findBySourceId(sourceId);

      expect(result.isOk()).toBe(true);
      const trackers = result.getValue();
      expect(trackers).toHaveLength(1);
      expect(trackers[0].filePath).toBe(validFilePath);
    });

    it('propagates Prisma errors', async () => {
      prismaFileTracker.findMany.mockRejectedValue(new Error('DB connection failed'));

      await expect(repository.findBySourceId('src-1')).rejects.toThrow('DB connection failed');
    });
  });

  describe('findExpiredBySourceId', () => {
    // Simulates a Prisma client that honors sourceId and createdAt lt filters.
    const stubFindManyLikePrisma = (rows: PrismaFileMemoryTrackerRecord[]) => {
      prismaFileTracker.findMany.mockImplementation(
        async (args: {
          where?: { sourceId?: string; createdAt?: { lt?: Date } };
          include?: { memories: boolean };
        }) => {
          const where = args?.where ?? {};
          return rows.filter(row => {
            if (where.sourceId !== undefined && row.sourceId !== where.sourceId) {
              return false;
            }
            if (where.createdAt?.lt !== undefined && !(row.createdAt < where.createdAt.lt)) {
              return false;
            }
            return true;
          });
        },
      );
    };

    it('returns only trackers with createdAt before cutoff for the given sourceId', async () => {
      const sourceId = 'src-1';
      const cutoff = new Date('2026-06-01T00:00:00.000Z');
      const expiredPath = '/test/expired.txt';
      const freshPath = '/test/fresh.txt';
      const expiredId = aFileMemoryTracker({ filePath: expiredPath }).toJson().id;
      const freshId = aFileMemoryTracker({ filePath: freshPath }).toJson().id;

      stubFindManyLikePrisma([
        aPrismaFileMemoryTracker({
          id: expiredId,
          filePath: expiredPath,
          sourceId,
          memoryBank: 'bank-a',
          createdAt: new Date('2026-01-15T00:00:00.000Z'),
          memories: [
            aPrismaFileMemoryTrackerMemory({ id: 9201n, memoryId: 'mem-001', fileTrackerId: expiredId }),
          ],
        }),
        aPrismaFileMemoryTracker({
          id: freshId,
          filePath: freshPath,
          sourceId,
          memoryBank: 'bank-a',
          createdAt: new Date('2026-07-01T00:00:00.000Z'),
          memories: [],
        }),
      ]);

      const result = await repository.findExpiredBySourceId(sourceId, cutoff);

      expect(prismaFileTracker.findMany).toHaveBeenCalledWith({
        where: { sourceId, createdAt: { lt: cutoff } },
        include: { memories: true },
      });
      expect(result.isOk()).toBe(true);
      const trackers = result.getValue();
      expect(trackers).toHaveLength(1);
      expect(trackers[0].filePath).toBe(expiredPath);
      expect(trackers[0].memoryIds).toEqual(['mem-001']);
    });

    it('excludes trackers whose createdAt equals the cutoff (lt, not lte)', async () => {
      const sourceId = 'src-1';
      const cutoff = new Date('2026-06-01T00:00:00.000Z');
      const boundaryPath = '/test/boundary.txt';
      const boundaryId = aFileMemoryTracker({ filePath: boundaryPath }).toJson().id;

      stubFindManyLikePrisma([
        aPrismaFileMemoryTracker({
          id: boundaryId,
          filePath: boundaryPath,
          sourceId,
          memoryBank: 'bank-a',
          createdAt: new Date(cutoff),
          memories: [],
        }),
      ]);

      const result = await repository.findExpiredBySourceId(sourceId, cutoff);

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual([]);
    });

    it("returns empty array when nothing expires and never returns other sources' trackers", async () => {
      const sourceId = 'src-1';
      const cutoff = new Date('2026-06-01T00:00:00.000Z');

      stubFindManyLikePrisma([
        // Expired, but belongs to another source.
        aPrismaFileMemoryTracker({
          filePath: '/test/other-source.txt',
          sourceId: 'src-2',
          memoryBank: 'bank-b',
          createdAt: new Date('2026-01-01T00:00:00.000Z'),
          memories: [],
        }),
        // Same source, but not yet expired.
        aPrismaFileMemoryTracker({
          filePath: '/test/same-source-fresh.txt',
          sourceId,
          memoryBank: 'bank-a',
          createdAt: new Date('2026-06-15T00:00:00.000Z'),
          memories: [],
        }),
      ]);

      const result = await repository.findExpiredBySourceId(sourceId, cutoff);

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual([]);
    });

    it('skips malformed rows and returns only valid trackers', async () => {
      const sourceId = 'src-1';
      const cutoff = new Date('2026-06-01T00:00:00.000Z');
      const validPath = '/test/valid.txt';
      const validId = aFileMemoryTracker({ filePath: validPath }).toJson().id;

      stubFindManyLikePrisma([
        aPrismaFileMemoryTracker({
          id: validId,
          filePath: validPath,
          sourceId,
          memoryBank: 'bank-a',
          createdAt: new Date('2026-01-15T00:00:00.000Z'),
          memories: [
            aPrismaFileMemoryTrackerMemory({ id: 9202n, memoryId: 'mem-001', fileTrackerId: validId }),
          ],
        }),
        // Malformed: empty filePath fails the aggregate schema.
        aPrismaFileMemoryTracker({
          id: aFileMemoryTracker().toJson().id,
          filePath: '',
          sourceId,
          memoryBank: 'bank-a',
          createdAt: new Date('2026-01-15T00:00:00.000Z'),
          memories: [],
        }),
      ]);

      const result = await repository.findExpiredBySourceId(sourceId, cutoff);

      expect(result.isOk()).toBe(true);
      const trackers = result.getValue();
      expect(trackers).toHaveLength(1);
      expect(trackers[0].filePath).toBe(validPath);
    });

    it('propagates Prisma errors', async () => {
      prismaFileTracker.findMany.mockRejectedValue(new Error('DB connection failed'));

      await expect(
        repository.findExpiredBySourceId('src-1', new Date('2026-06-01T00:00:00.000Z')),
      ).rejects.toThrow('DB connection failed');
    });
  });

  describe('findCreatedAtByFilePath', () => {
    it('returns the createdAt of the tracker for the given filePath', async () => {
      const createdAt = new Date('2026-01-15T00:00:00.000Z');
      prismaFileTracker.findUnique.mockResolvedValue({
        filePath: '/test/file.txt',
        createdAt,
      });

      const result = await repository.findCreatedAtByFilePath('/test/file.txt');

      expect(prismaFileTracker.findUnique).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
        select: { createdAt: true },
      });
      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual(createdAt);
    });

    it('returns Result.ok(null) when no tracker exists for the filePath', async () => {
      prismaFileTracker.findUnique.mockResolvedValue(null);

      const result = await repository.findCreatedAtByFilePath('/nonexistent/file.txt');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toBeNull();
    });

    it('propagates Prisma errors', async () => {
      prismaFileTracker.findUnique.mockRejectedValue(new Error('DB connection failed'));

      await expect(repository.findCreatedAtByFilePath('/test/file.txt')).rejects.toThrow(
        'DB connection failed',
      );
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
    it('updates both fileHash and hardwareId when both provided and clears skipReason alongside the hash', async () => {
      prismaFileTracker.updateMany.mockResolvedValue({ count: 1 });

      await repository.updateFileTrackerHash('/test/file.txt', 'sha256-abc', 'hw-123');

      expect(prismaFileTracker.updateMany).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
        data: { fileHash: 'sha256-abc', hardwareId: 'hw-123', skipReason: null },
      });
    });

    it('updates only fileHash when hardwareId is undefined (still clears skipReason)', async () => {
      prismaFileTracker.updateMany.mockResolvedValue({ count: 1 });

      await repository.updateFileTrackerHash('/test/file.txt', 'sha256-abc', undefined);

      expect(prismaFileTracker.updateMany).toHaveBeenCalledWith({
        where: { filePath: '/test/file.txt' },
        data: { fileHash: 'sha256-abc', skipReason: null },
      });
    });

    it('updates only hardwareId when fileHash is undefined — no skipReason write without a hash', async () => {
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
        data: { fileHash: '', hardwareId: 'hw-123', skipReason: null },
      });
    });
  });

  describe('findHashAndSkipReasonByFilePath', () => {
    it('returns Result.ok(null) for an untracked filePath (no FileTracker row)', async () => {
      prismaFileTracker.findUnique.mockResolvedValue(null);

      const result = await repository.findHashAndSkipReasonByFilePath('/nonexistent/file.txt');

      expect(prismaFileTracker.findUnique).toHaveBeenCalledWith({
        where: { filePath: '/nonexistent/file.txt' },
        select: { fileHash: true, skipReason: true },
      });
      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toBeNull();
    });

    it('passes fileHash and skipReason through exactly for a tracked terminal-skip row', async () => {
      prismaFileTracker.findUnique.mockResolvedValue({
        fileHash: 'sha-known-abc',
        skipReason: 'zero-chunks',
      });

      const result = await repository.findHashAndSkipReasonByFilePath('/skip/file.txt');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual({ fileHash: 'sha-known-abc', skipReason: 'zero-chunks' });
    });

    it('passes null columns through for a tracked row without hash or skip reason', async () => {
      prismaFileTracker.findUnique.mockResolvedValue({
        fileHash: null,
        skipReason: null,
      });

      const result = await repository.findHashAndSkipReasonByFilePath('/legacy/file.txt');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual({ fileHash: null, skipReason: null });
    });

    it('converts a Prisma read failure into Result.ko instead of throwing', async () => {
      prismaFileTracker.findUnique.mockRejectedValue(new Error('DB connection failed'));

      const result = await repository.findHashAndSkipReasonByFilePath('/test/file.txt');

      expect(result.isKo()).toBe(true);
      expect(result.getErrors()[0].message).toContain('DB connection failed');
    });
  });
});

describe('FileMemoryTrackerRepository — upsertTerminalSkip', () => {
  // Stateful FileTracker-table fake; its fileMemoryTracker mock is wired but
  // never expected to be called — a terminal skip must never touch memory rows.
  async function buildRepositoryWithFileTrackerTable(
    seeds: Parameters<typeof aFileTrackerTableFake>[0] = [],
  ) {
    const fake = aFileTrackerTableFake(seeds);

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        FileMemoryTrackerRepository,
        {
          provide: PrismaService,
          useValue: { fileTracker: fake.fileTracker, fileMemoryTracker: fake.fileMemoryTracker },
        },
      ],
    }).compile();

    return { repository: module.get<FileMemoryTrackerRepository>(FileMemoryTrackerRepository), fake };
  }

  function expectNoMemoryModelOps(
    fileMemoryTracker: ReturnType<typeof aFileTrackerTableFake>['fileMemoryTracker'],
  ) {
    for (const op of Object.values(fileMemoryTracker)) {
      expect(op).not.toHaveBeenCalled();
    }
  }

  it('creates the FileTracker row with hash, hardwareId and skipReason and zero FileMemoryTracker writes', async () => {
    const { repository, fake } = await buildRepositoryWithFileTrackerTable();

    const result = await repository.upsertTerminalSkip(
      '/skip/zero-chunks.txt',
      'src-1',
      'bank-a',
      'sha-skip-1',
      'hw-9',
      'zero-chunks',
    );

    expect(result.isOk()).toBe(true);
    expect(fake.rows).toHaveLength(1);
    expect(fake.rows[0]).toMatchObject({
      filePath: '/skip/zero-chunks.txt',
      sourceId: 'src-1',
      memoryBank: 'bank-a',
      fileHash: 'sha-skip-1',
      hardwareId: 'hw-9',
      skipReason: 'zero-chunks',
    });
    expect(typeof fake.rows[0].id).toBe('bigint');
    expect(fake.fileTracker.upsert).toHaveBeenCalledWith(
      expect.objectContaining({ where: { filePath: '/skip/zero-chunks.txt' } }),
    );
    expectNoMemoryModelOps(fake.fileMemoryTracker);
  });

  it('updates an existing row in place (hash/hardwareId/skipReason) without creating a second row and without touching its memories', async () => {
    const filePath = '/skip/grew.txt';
    const { repository, fake } = await buildRepositoryWithFileTrackerTable([
      {
        id: 5001n,
        filePath,
        sourceId: 'orig-src',
        memoryBank: 'orig-bank',
        fileHash: 'sha-old',
        hardwareId: null,
        skipReason: 'empty-content',
        memories: [{ id: 7001n, memoryId: 'mem-keep', fileTrackerId: 5001n }],
      },
    ]);

    const result = await repository.upsertTerminalSkip(
      filePath,
      'other-src',
      'other-bank',
      'sha-new',
      'hw-2',
      'zero-chunks',
    );

    expect(result.isOk()).toBe(true);
    expect(fake.rows).toHaveLength(1);
    expect(fake.rows[0]).toMatchObject({
      id: 5001n,
      fileHash: 'sha-new',
      hardwareId: 'hw-2',
      skipReason: 'zero-chunks',
    });
    // The update path sets only fileHash/hardwareId/skipReason — identity and
    // association columns of the existing row are left untouched.
    expect(fake.rows[0].sourceId).toBe('orig-src');
    expect(fake.rows[0].memoryBank).toBe('orig-bank');
    // Memory side of the row is undamaged.
    expect(fake.rows[0].memories).toEqual([{ id: 7001n, memoryId: 'mem-keep', fileTrackerId: 5001n }]);
    expectNoMemoryModelOps(fake.fileMemoryTracker);
  });

  it('converts a Prisma write failure into Result.ko instead of throwing', async () => {
    const { repository, fake } = await buildRepositoryWithFileTrackerTable();
    fake.fileTracker.upsert.mockRejectedValue(new Error('SQLITE_BUSY'));

    const result = await repository.upsertTerminalSkip(
      '/skip/busy.txt',
      'src-1',
      'bank-a',
      'sha-1',
      null,
      'content-filtered',
    );

    expect(result.isKo()).toBe(true);
    expect(result.getErrors()[0].message).toContain('SQLITE_BUSY');
    expectNoMemoryModelOps(fake.fileMemoryTracker);
  });
});

describe('FileMemoryTrackerRepository — successful ingest clears skip rows (spec C3 step 5)', () => {
  async function buildRepositoryWithFileTrackerTable(
    seeds: Parameters<typeof aFileTrackerTableFake>[0] = [],
  ) {
    const fake = aFileTrackerTableFake(seeds);

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        FileMemoryTrackerRepository,
        {
          provide: PrismaService,
          useValue: { fileTracker: fake.fileTracker, fileMemoryTracker: fake.fileMemoryTracker },
        },
      ],
    }).compile();

    return { repository: module.get<FileMemoryTrackerRepository>(FileMemoryTrackerRepository), fake };
  }

  async function readBackState(repository: FileMemoryTrackerRepository, filePath: string) {
    const result = await repository.findHashAndSkipReasonByFilePath(filePath);
    expect(result.isOk()).toBe(true);
    return result.getValue();
  }

  it('writing a new fileHash nulls skipReason on the end-state row (terminal skip cleared by change + reingest)', async () => {
    const filePath = '/skip/grew-then-ingested.txt';
    const { repository } = await buildRepositoryWithFileTrackerTable([
      {
        filePath,
        fileHash: 'sha-of-skipped-bytes',
        hardwareId: 'hw-old',
        skipReason: 'empty-content',
      },
    ]);

    await repository.updateFileTrackerHash(filePath, 'sha-new-content', 'hw-new');

    expect(await readBackState(repository, filePath)).toEqual({
      fileHash: 'sha-new-content',
      skipReason: null,
    });
  });

  it('a row without skipReason: hash update leaves skipReason null (no new behavior)', async () => {
    const filePath = '/normally-ingested.txt';
    const { repository } = await buildRepositoryWithFileTrackerTable([
      { filePath, fileHash: 'sha-old', skipReason: null },
    ]);

    await repository.updateFileTrackerHash(filePath, 'sha-rotated', undefined);

    expect(await readBackState(repository, filePath)).toEqual({
      fileHash: 'sha-rotated',
      skipReason: null,
    });
  });

  it('hardwareId-only update does NOT clear a recorded skip reason (clearing is bound to the hash write)', async () => {
    const filePath = '/still-skipped.txt';
    const { repository } = await buildRepositoryWithFileTrackerTable([
      { filePath, fileHash: 'sha-skipped', skipReason: 'zero-chunks' },
    ]);

    await repository.updateFileTrackerHash(filePath, undefined, 'hw-later');

    expect(await readBackState(repository, filePath)).toEqual({
      fileHash: 'sha-skipped',
      skipReason: 'zero-chunks',
    });
  });
});
