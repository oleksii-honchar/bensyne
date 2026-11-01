/**
 * Test utilities for FileMemoryTrackerRepository.
 * Provides mock implementations for testing without real Prisma database.
 */

import { FileMemoryTracker } from '@/domain/file-memory-tracker.aggregate';
import { generateId } from '@/utils/big-endian-id';
import { Result } from '@/utils/result';
import { faker } from '@/utils/test-faker';

/**
 * Aggregate-level test builder for FileMemoryTracker domain entity.
 * Uses faker for randomized but deterministic values (seed 42).
 */
export function aFileMemoryTracker(
  overrides?: Partial<{
    id: bigint;
    filePath: string;
    memoryIds: string[];
    sourceId: string;
    memoryBank: string;
  }>,
): FileMemoryTracker {
  const result = FileMemoryTracker.of({
    id: generateId(),
    filePath: faker.system.filePath(),
    memoryIds: [],
    sourceId: faker.string.alphanumeric(12),
    memoryBank: faker.word.adjective(),
    ...overrides,
  });
  return result.getValue();
}

export interface PrismaFileMemoryTrackerRecord {
  id: bigint;
  filePath: string;
  sourceId: string;
  memoryBank: string;
  createdAt: Date;
  updatedAt: Date;
  memories: { id: bigint; memoryId: string; fileTrackerId: bigint }[];
}

export interface PrismaFileMemoryTrackerMemoryRecord {
  id: bigint;
  memoryId: string;
  fileTrackerId: bigint;
  createdAt: Date;
}

export function aPrismaFileMemoryTracker(
  overrides?: Partial<PrismaFileMemoryTrackerRecord>,
): PrismaFileMemoryTrackerRecord {
  return {
    id: generateId(),
    filePath: faker.system.filePath(),
    sourceId: faker.string.alphanumeric(12),
    memoryBank: faker.word.adjective(),
    createdAt: new Date('2026-01-01T00:00:00.000Z'),
    updatedAt: new Date('2026-01-01T00:00:00.000Z'),
    memories: [],
    ...overrides,
  };
}

export function aPrismaFileMemoryTrackerMemory(
  overrides?: Partial<PrismaFileMemoryTrackerMemoryRecord>,
): PrismaFileMemoryTrackerMemoryRecord {
  return {
    id: generateId(),
    memoryId: faker.string.uuid(),
    fileTrackerId: generateId(),
    createdAt: new Date('2026-01-01T00:00:00.000Z'),
    ...overrides,
  };
}

/**
 * A single row of the in-memory FileTracker table fake.
 * Mirrors the FileTracker columns (incl. the nullable skipReason) as the
 * generated Prisma client exposes them.
 */
export interface FakeFileTrackerRow {
  id: bigint;
  filePath: string;
  sourceId: string;
  memoryBank: string;
  fileHash: string | null;
  hardwareId: string | null;
  skipReason: string | null;
  createdAt: Date;
  updatedAt: Date;
  memories: { id: bigint; memoryId: string; fileTrackerId: bigint }[];
}

/**
 * Stateful fake of the Prisma FileTracker table honoring the subset of Prisma
 * semantics used by the ingest-gate reads and the terminal-skip write:
 * findUnique by where.filePath (with optional select projection) and upsert
 * keyed on where.filePath (update is an in-place partial merge). Exposes the
 * row store for behavioral assertions and a never-wired fileMemoryTracker
 * mock so tests can assert zero FileMemoryTracker (memory-model) operations.
 */
export function aFileTrackerTableFake(seeds: Partial<FakeFileTrackerRow>[] = []) {
  const rows: FakeFileTrackerRow[] = seeds.map(seed => ({
    id: generateId(),
    filePath: faker.system.filePath(),
    sourceId: faker.string.alphanumeric(12),
    memoryBank: faker.word.adjective(),
    fileHash: null,
    hardwareId: null,
    skipReason: null,
    createdAt: new Date('2026-01-01T00:00:00.000Z'),
    updatedAt: new Date('2026-01-01T00:00:00.000Z'),
    memories: [],
    ...seed,
  }));

  const fileTracker = {
    findUnique: jest.fn(async (args: { where: { filePath: string }; select?: Record<string, boolean> }) => {
      const row = rows.find(r => r.filePath === args.where.filePath);
      if (!row) {
        return null;
      }
      if (args.select) {
        const projected: Record<string, unknown> = {};
        for (const key of Object.keys(args.select)) {
          projected[key] = (row as unknown as Record<string, unknown>)[key];
        }
        return projected;
      }
      return row;
    }),
    upsert: jest.fn(
      async (args: {
        where: { filePath: string };
        create: Partial<FakeFileTrackerRow>;
        update: Partial<FakeFileTrackerRow>;
      }) => {
        const index = rows.findIndex(r => r.filePath === args.where.filePath);
        if (index >= 0) {
          rows[index] = { ...rows[index], ...args.update };
          return { ...rows[index] };
        }
        const created: FakeFileTrackerRow = {
          id: generateId(),
          filePath: args.where.filePath,
          sourceId: '',
          memoryBank: '',
          fileHash: null,
          hardwareId: null,
          skipReason: null,
          createdAt: new Date('2026-01-01T00:00:00.000Z'),
          updatedAt: new Date('2026-01-01T00:00:00.000Z'),
          memories: [],
          ...args.create,
        };
        rows.push(created);
        return { ...created, memories: [] };
      },
    ),
    findMany: jest.fn(),
    delete: jest.fn(),
    // Stateful updateMany (subset of Prisma semantics): partial-merges data
    // into rows matching where.filePath and returns { count } — lets tests
    // assert end-state row behavior (e.g. skipReason cleared by a hash write).
    updateMany: jest.fn(async (args: { where: { filePath: string }; data: Record<string, unknown> }) => {
      let count = 0;
      for (let i = 0; i < rows.length; i++) {
        if (rows[i].filePath === args.where.filePath) {
          rows[i] = { ...rows[i], ...args.data };
          count++;
        }
      }
      return { count };
    }),
  };

  const fileMemoryTracker = {
    create: jest.fn(),
    upsert: jest.fn(),
    deleteMany: jest.fn(),
    update: jest.fn(),
    updateMany: jest.fn(),
    delete: jest.fn(),
  };

  return { rows, fileTracker, fileMemoryTracker };
}

/**
 * Returns a stub FileMemoryTrackerRepository that resolves all calls with safe defaults.
 */
export function aFileMemoryTrackerRepositoryService() {
  return {
    findByFilePath: jest.fn().mockResolvedValue(null),
    findBySourceId: jest.fn().mockResolvedValue([]),
    findExpiredBySourceId: jest.fn().mockResolvedValue([]),
    findCreatedAtByFilePath: jest.fn().mockResolvedValue(null),
    findHashAndSkipReasonByFilePath: jest.fn().mockResolvedValue(Result.ok(null)),
    upsertTerminalSkip: jest.fn().mockResolvedValue(Result.ok(undefined)),
    findOrCreate: jest
      .fn()
      .mockImplementation((tracker: FileMemoryTracker) =>
        Promise.resolve({ isOk: () => true, isKo: () => false, getValue: () => tracker }),
      ),
    save: jest
      .fn()
      .mockImplementation((tracker: FileMemoryTracker) =>
        Promise.resolve({ isOk: () => true, isKo: () => false, getValue: () => tracker }),
      ),
    upsert: jest
      .fn()
      .mockImplementation((tracker: FileMemoryTracker) =>
        Promise.resolve({ isOk: () => true, isKo: () => false, getValue: () => tracker }),
      ),
    getMemoryIds: jest.fn().mockResolvedValue([]),
    deleteByFilePath: jest.fn().mockResolvedValue(undefined),
    updateFileTrackerHash: jest.fn().mockResolvedValue(undefined),
  };
}
