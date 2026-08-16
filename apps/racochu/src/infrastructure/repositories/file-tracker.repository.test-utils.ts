/**
 * Test utilities for FileTrackerRepository.
 * Provides mock implementations for testing without real Prisma database.
 */

import { generateId } from '@/utils/big-endian-id';
import { faker } from '@/utils/test-faker';

export interface PrismaFileTrackerRecord {
  id: bigint;
  filePath: string;
  sourceId: string;
  memoryBank: string;
  createdAt: Date;
  updatedAt: Date;
  memories: { id: bigint; memoryId: string; fileTrackerId: bigint }[];
}

export interface PrismaFileTrackerMemoryRecord {
  id: bigint;
  memoryId: string;
  fileTrackerId: bigint;
  createdAt: Date;
}

/**
 * Create a Prisma FileTracker record with faker defaults and overrides.
 */
export function aPrismaFileTracker(overrides?: Partial<PrismaFileTrackerRecord>): PrismaFileTrackerRecord {
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

/**
 * Create a Prisma FileTracker memory record with faker defaults and overrides.
 */
export function aPrismaFileTrackerMemory(
  overrides?: Partial<PrismaFileTrackerMemoryRecord>,
): PrismaFileTrackerMemoryRecord {
  return {
    id: generateId(),
    memoryId: faker.string.uuid(),
    fileTrackerId: generateId(),
    createdAt: new Date('2026-01-01T00:00:00.000Z'),
    ...overrides,
  };
}

/**
 * Create a mock Prisma fileTracker client with jest mocks.
 */
export function aMockPrismaFileTracker() {
  return {
    findUnique: jest.fn(),
    upsert: jest.fn(),
    delete: jest.fn(),
    updateMany: jest.fn(),
  };
}

/**
 * Create a mock Prisma fileMemoryTracker client with jest mocks.
 */
export function aMockPrismaFileMemoryTracker() {
  return {
    create: jest.fn(),
    upsert: jest.fn(),
    deleteMany: jest.fn(),
  };
}
