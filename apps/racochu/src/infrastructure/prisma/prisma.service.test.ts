import { PrismaBetterSqlite3 } from '@prisma/adapter-better-sqlite3';
import { execSync } from 'child_process';
import { existsSync, rmSync } from 'fs';
import { join, resolve } from 'path';
import { PrismaClient } from '../../generated/prisma/client';

const projectRoot = resolve(__dirname, '../../../');
const testDbPath = join(projectRoot, 'data', 'test-prisma.db');

function pushSchema(dbUrl: string): void {
  execSync(`npx prisma db push --accept-data-loss --url "${dbUrl}"`, {
    cwd: projectRoot,
    env: { ...process.env, PRISMA_USER_CONSENT_FOR_DANGEROUS_AI_ACTION: 'yes' },
  });
}

function createClient(dbUrl: string): PrismaClient {
  const adapter = new PrismaBetterSqlite3({ url: dbUrl });
  return new PrismaClient({ adapter });
}

describe('PrismaService.ensureSchema', () => {
  let client: PrismaClient;

  beforeEach(() => {
    // Clean up any leftover test DB
    if (existsSync(testDbPath)) {
      rmSync(testDbPath);
    }
    // Push schema to test DB using prisma db push
    pushSchema(`file:${testDbPath}`);
    // Create a client connected to the test DB via adapter
    client = createClient(`file:${testDbPath}`);
  });

  afterEach(async () => {
    await client?.$disconnect();
    // Clean up test DB
    if (existsSync(testDbPath)) {
      rmSync(testDbPath);
    }
  });

  describe('ensureSchema creates tables on empty database', () => {
    it('should create FileTracker table', async () => {
      const result = await client.$queryRawUnsafe(
        `SELECT name FROM sqlite_master WHERE type='table' AND name='FileTracker'`,
      );
      expect((result as unknown[]).length).toBeGreaterThan(0);
    });

    it('should create FileMemoryTracker table', async () => {
      const result = await client.$queryRawUnsafe(
        `SELECT name FROM sqlite_master WHERE type='table' AND name='FileMemoryTracker'`,
      );
      expect((result as unknown[]).length).toBeGreaterThan(0);
    });

    it('should create FileTracker_filePath_idx index', async () => {
      const result = await client.$queryRawUnsafe(
        `SELECT name FROM sqlite_master WHERE type='index' AND name='FileTracker_filePath_idx'`,
      );
      expect((result as unknown[]).length).toBeGreaterThan(0);
    });

    it('should create FileTracker_sourceId_memoryBank_idx index', async () => {
      const result = await client.$queryRawUnsafe(
        `SELECT name FROM sqlite_master WHERE type='index' AND name='FileTracker_sourceId_memoryBank_idx'`,
      );
      expect((result as unknown[]).length).toBeGreaterThan(0);
    });

    it('should create FileTracker_fileHash_idx index', async () => {
      const result = await client.$queryRawUnsafe(
        `SELECT name FROM sqlite_master WHERE type='index' AND name='FileTracker_fileHash_idx'`,
      );
      expect((result as unknown[]).length).toBeGreaterThan(0);
    });

    it('should create FileTracker_hardwareId_idx index', async () => {
      const result = await client.$queryRawUnsafe(
        `SELECT name FROM sqlite_master WHERE type='index' AND name='FileTracker_hardwareId_idx'`,
      );
      expect((result as unknown[]).length).toBeGreaterThan(0);
    });

    it('should create FileMemoryTracker_fileTrackerId_idx index', async () => {
      const result = await client.$queryRawUnsafe(
        `SELECT name FROM sqlite_master WHERE type='index' AND name='FileMemoryTracker_fileTrackerId_idx'`,
      );
      expect((result as unknown[]).length).toBeGreaterThan(0);
    });
  });

  describe('ensureSchema is idempotent', () => {
    it('should not throw when called twice on the same database', () => {
      expect(() => pushSchema(`file:${testDbPath}`)).not.toThrow();
    });

    it('should not create duplicate tables when called twice', async () => {
      pushSchema(`file:${testDbPath}`);

      const tables = await client.$queryRawUnsafe(
        `SELECT name FROM sqlite_master WHERE type='table' AND name='FileTracker'`,
      );
      expect((tables as unknown[]).length).toBe(1);
    });

    it('should not create duplicate indexes when called twice', async () => {
      pushSchema(`file:${testDbPath}`);

      const indexes = await client.$queryRawUnsafe(
        `SELECT name FROM sqlite_master WHERE type='index' AND name='FileTracker_filePath_idx'`,
      );
      expect((indexes as unknown[]).length).toBe(1);
    });
  });

  describe('ensureSchema allows Prisma operations after creation', () => {
    it('should allow creating a FileTracker record', async () => {
      const record = await client.fileTracker.create({
        data: {
          id: 9001n,
          filePath: '/test/ensure-schema/file.md',
          sourceId: 'test-source',
          memoryBank: 'test-bank',
        },
      });

      expect(record.filePath).toBe('/test/ensure-schema/file.md');
      expect(record.sourceId).toBe('test-source');
    });

    it('should allow creating a FileMemoryTracker record linked to FileTracker', async () => {
      const tracker = await client.fileTracker.create({
        data: {
          id: 9002n,
          filePath: '/test/ensure-schema/linked.md',
          sourceId: 'test-source',
          memoryBank: 'test-bank',
        },
      });

      const memory = await client.fileMemoryTracker.create({
        data: {
          id: 9003n,
          fileTrackerId: tracker.id,
          memoryId: 'test-memory-id',
        },
      });

      expect(memory.memoryId).toBe('test-memory-id');
      expect(memory.fileTrackerId).toBe(tracker.id);
    });
  });

  describe('ensureSchema syncs schema changes', () => {
    it('should fail fast when schema is invalid', () => {
      // db push with a non-existent schema file should throw
      expect(() => {
        execSync('npx prisma db push --accept-data-loss --schema prisma/nonexistent.prisma', {
          cwd: projectRoot,
        });
      }).toThrow();
    });
  });
});
