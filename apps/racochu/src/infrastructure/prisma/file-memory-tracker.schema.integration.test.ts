import { PrismaBetterSqlite3 } from '@prisma/adapter-better-sqlite3';
import { existsSync, mkdirSync, rmSync } from 'fs';
import { join } from 'path';
import { PrismaClient } from '../../generated/prisma/client';

describe('FileTracker and FileMemoryTracker Schema Integration', () => {
  let prisma: PrismaClient;
  const testDbPath = join(__dirname, 'test-file-tracker.db');

  beforeAll(async () => {
    const dataDir = join(__dirname, '..', '..', '..', 'data');
    if (!existsSync(dataDir)) {
      mkdirSync(dataDir, { recursive: true });
    }

    const adapter = new PrismaBetterSqlite3({ url: `file:${testDbPath}` });
    prisma = new PrismaClient({ adapter });
    await prisma.$connect();

    // Create FileTracker table
    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "FileTracker" (
        "id" INTEGER NOT NULL,
        "filePath" TEXT NOT NULL,
        "sourceId" TEXT NOT NULL,
        "memoryBank" TEXT NOT NULL,
        "fileHash" TEXT,
        "hardwareId" TEXT,
        "createdAt" DATETIME NOT NULL DEFAULT (datetime('now')),
        "updatedAt" DATETIME NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY ("id"),
        UNIQUE ("filePath")
      )
    `);

    // Create FileMemoryTracker table
    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "FileMemoryTracker" (
        "id" INTEGER NOT NULL,
        "memoryId" TEXT NOT NULL,
        "fileTrackerId" INTEGER NOT NULL,
        "createdAt" DATETIME NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY ("id"),
        UNIQUE ("fileTrackerId", "memoryId"),
        FOREIGN KEY ("fileTrackerId") REFERENCES "FileTracker"("id") ON DELETE CASCADE
      )
    `);

    await prisma.$executeRawUnsafe(
      `CREATE INDEX IF NOT EXISTS "FileTracker_filePath_idx" ON "FileTracker" ("filePath")`,
    );
    await prisma.$executeRawUnsafe(
      `CREATE INDEX IF NOT EXISTS "FileTracker_sourceId_memoryBank_idx" ON "FileTracker" ("sourceId", "memoryBank")`,
    );
    await prisma.$executeRawUnsafe(
      `CREATE INDEX IF NOT EXISTS "FileTracker_fileHash_idx" ON "FileTracker" ("fileHash")`,
    );
    await prisma.$executeRawUnsafe(
      `CREATE INDEX IF NOT EXISTS "FileTracker_hardwareId_idx" ON "FileTracker" ("hardwareId")`,
    );
    await prisma.$executeRawUnsafe(
      `CREATE INDEX IF NOT EXISTS "FileMemoryTracker_fileTrackerId_idx" ON "FileMemoryTracker" ("fileTrackerId")`,
    );
  });

  afterAll(async () => {
    await prisma.$disconnect();
    if (existsSync(testDbPath)) {
      rmSync(testDbPath);
    }
  });

  it('should have FileTracker and FileMemoryTracker models available in Prisma client', async () => {
    expect(prisma.fileTracker).toBeDefined();
    expect(typeof prisma.fileTracker.create).toBe('function');
    expect(typeof prisma.fileTracker.findUnique).toBe('function');
    expect(typeof prisma.fileTracker.upsert).toBe('function');
    expect(typeof prisma.fileTracker.delete).toBe('function');

    expect(prisma.fileMemoryTracker).toBeDefined();
    expect(typeof prisma.fileMemoryTracker.create).toBe('function');
    expect(typeof prisma.fileMemoryTracker.upsert).toBe('function');
  });

  it('should create a FileTracker record with all fields', async () => {
    const record = await prisma.fileTracker.create({
      data: {
        id: 1001n,
        filePath: '/test/path/to/file.md',
        sourceId: 'source-1',
        memoryBank: 'test-namespace',
      },
    });

    expect(record.id).toBeDefined();
    expect(record.id).toBe(1001n);
    expect(typeof record.id).toBe('bigint');
    expect(record.filePath).toBe('/test/path/to/file.md');
    expect(record.sourceId).toBe('source-1');
    expect(record.memoryBank).toBe('test-namespace');
    expect(record.createdAt).toBeInstanceOf(Date);
    expect(record.updatedAt).toBeInstanceOf(Date);
  });

  it('should enforce unique constraint on filePath', async () => {
    await prisma.fileTracker.create({
      data: {
        id: 1002n,
        filePath: '/unique/test/file.txt',
        sourceId: 'source-1',
        memoryBank: 'test',
      },
    });

    await expect(
      prisma.fileTracker.create({
        data: {
          id: 1003n,
          filePath: '/unique/test/file.txt',
          sourceId: 'source-2',
          memoryBank: 'test',
        },
      }),
    ).rejects.toThrow();
  });

  it('should find by filePath using unique constraint', async () => {
    const found = await prisma.fileTracker.findUnique({
      where: { filePath: '/test/path/to/file.md' },
    });

    expect(found).not.toBeNull();
    expect(found!.id).toBe(1001n);
    expect(found!.sourceId).toBe('source-1');
  });

  it('should support querying by sourceId and memoryBank via index', async () => {
    const records = await prisma.fileTracker.findMany({
      where: { sourceId: 'source-1', memoryBank: 'test-namespace' },
    });

    expect(records.length).toBeGreaterThanOrEqual(1);
  });

  it('should update updatedAt on record modification', async () => {
    const before = await prisma.fileTracker.findUnique({
      where: { filePath: '/test/path/to/file.md' },
    });
    expect(before).not.toBeNull();

    await new Promise(resolve => setTimeout(resolve, 10));

    const after = await prisma.fileTracker.update({
      where: { filePath: '/test/path/to/file.md' },
      data: { sourceId: 'source-updated' },
    });

    expect(after.updatedAt.getTime()).toBeGreaterThanOrEqual(before!.updatedAt.getTime());
    expect(after.sourceId).toBe('source-updated');
  });

  it('should delete a FileTracker record and cascade delete memories', async () => {
    const tracker = await prisma.fileTracker.create({
      data: {
        id: 1004n,
        filePath: '/cascade/test/file.md',
        sourceId: 'source-1',
        memoryBank: 'test',
      },
    });

    await prisma.fileMemoryTracker.create({
      data: {
        id: 2001n,
        fileTrackerId: tracker.id,
        memoryId: 'mem-cascade-1',
      },
    });

    await prisma.fileTracker.delete({
      where: { filePath: '/cascade/test/file.md' },
    });

    const found = await prisma.fileTracker.findUnique({
      where: { filePath: '/cascade/test/file.md' },
    });
    expect(found).toBeNull();

    const remainingMemories = await prisma.fileMemoryTracker.findMany({
      where: { fileTrackerId: tracker.id },
    });
    expect(remainingMemories).toHaveLength(0);
  });

  it('should create FileMemoryTracker linked to FileTracker', async () => {
    const tracker = await prisma.fileTracker.create({
      data: {
        id: 1005n,
        filePath: '/memory/test/file.md',
        sourceId: 'source-1',
        memoryBank: 'test',
      },
    });

    const memory = await prisma.fileMemoryTracker.create({
      data: {
        id: 2002n,
        fileTrackerId: tracker.id,
        memoryId: 'mem-test-1',
      },
    });

    expect(memory.id).toBeDefined();
    expect(memory.id).toBe(2002n);
    expect(memory.memoryId).toBe('mem-test-1');
    expect(memory.fileTrackerId).toBe(tracker.id);
  });

  it('should enforce unique constraint on fileTrackerId+memoryId', async () => {
    const tracker = await prisma.fileTracker.create({
      data: {
        id: 1006n,
        filePath: '/unique-memory/test/file.md',
        sourceId: 'source-1',
        memoryBank: 'test',
      },
    });

    await prisma.fileMemoryTracker.create({
      data: {
        id: 2003n,
        fileTrackerId: tracker.id,
        memoryId: 'mem-unique-1',
      },
    });

    await expect(
      prisma.fileMemoryTracker.create({
        data: {
          id: 2004n,
          fileTrackerId: tracker.id,
          memoryId: 'mem-unique-1',
        },
      }),
    ).rejects.toThrow();
  });

  it('should upsert FileMemoryTracker without error on duplicate', async () => {
    const tracker = await prisma.fileTracker.create({
      data: {
        id: 1007n,
        filePath: '/upsert-memory/test/file.md',
        sourceId: 'source-1',
        memoryBank: 'test',
      },
    });

    await prisma.fileMemoryTracker.upsert({
      where: {
        fileTrackerId_memoryId: {
          fileTrackerId: tracker.id,
          memoryId: 'mem-upsert-1',
        },
      },
      create: {
        id: 2005n,
        fileTrackerId: tracker.id,
        memoryId: 'mem-upsert-1',
      },
      update: {},
    });

    // Second upsert should not throw
    await prisma.fileMemoryTracker.upsert({
      where: {
        fileTrackerId_memoryId: {
          fileTrackerId: tracker.id,
          memoryId: 'mem-upsert-1',
        },
      },
      create: {
        id: 2006n,
        fileTrackerId: tracker.id,
        memoryId: 'mem-upsert-1',
      },
      update: {},
    });

    const count = await prisma.fileMemoryTracker.count({
      where: { fileTrackerId: tracker.id, memoryId: 'mem-upsert-1' },
    });
    expect(count).toBe(1);
  });

  it('should include memories when querying FileTracker with include', async () => {
    const tracker = await prisma.fileTracker.create({
      data: {
        id: 1008n,
        filePath: '/include/test/file.md',
        sourceId: 'source-1',
        memoryBank: 'test',
      },
    });

    await prisma.fileMemoryTracker.create({
      data: { id: 2007n, fileTrackerId: tracker.id, memoryId: 'mem-inc-1' },
    });
    await prisma.fileMemoryTracker.create({
      data: { id: 2008n, fileTrackerId: tracker.id, memoryId: 'mem-inc-2' },
    });

    const found = await prisma.fileTracker.findUnique({
      where: { filePath: '/include/test/file.md' },
      include: { memories: true },
    });

    expect(found).not.toBeNull();
    expect(found!.memories).toHaveLength(2);
    const memoryIds = found!.memories.map(m => m.memoryId);
    expect(memoryIds).toContain('mem-inc-1');
    expect(memoryIds).toContain('mem-inc-2');
  });

  it('should upsert FileTracker creating or updating', async () => {
    // Create via upsert
    const created = await prisma.fileTracker.upsert({
      where: { filePath: '/upsert-tracker/file.md' },
      create: {
        id: 1009n,
        filePath: '/upsert-tracker/file.md',
        sourceId: 'source-create',
        memoryBank: 'test',
      },
      update: {
        sourceId: 'source-update',
      },
    });

    expect(created.sourceId).toBe('source-create');

    // Update via upsert
    const updated = await prisma.fileTracker.upsert({
      where: { filePath: '/upsert-tracker/file.md' },
      create: {
        id: 1010n,
        filePath: '/upsert-tracker/file.md',
        sourceId: 'source-should-not-use',
        memoryBank: 'test',
      },
      update: {
        sourceId: 'source-update',
      },
    });

    expect(updated.sourceId).toBe('source-update');
    expect(updated.id).toBe(created.id);
  });
});
