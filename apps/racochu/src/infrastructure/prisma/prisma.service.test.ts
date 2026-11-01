import { PrismaBetterSqlite3 } from '@prisma/adapter-better-sqlite3';
import { execSync } from 'child_process';
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs';
import { createRequire } from 'module';
import { tmpdir } from 'os';
import { join, resolve } from 'path';
import { PrismaClient } from '../../generated/prisma/client';

import { findProjectRoot, PrismaService } from './prisma.service';

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

// ── Task 7 / spec C5: migrate deploy + fail-loud dedup count guard ──────────
// The constructor options below are the test seams (spec C5 "Design for
// testability"): `execSchemaCommand` captures the composed schema command,
// `readFileTrackerCount` scripts the count source, `dataDir` isolates the
// adapter from the real project data dir. Defaults must keep production wiring.
interface SchemaCommandOptions {
  cwd: string;
  stdio: 'inherit';
  env?: Record<string, string | undefined>;
}
// Standalone structural view of the service under test (a PrismaService ∩
// public-ensureSchema intersection collapses to `never` because the current
// ensureSchema is private — the point of these tests is to make it public).
interface EnsureSchemaService {
  ensureSchema(): void;
  onModuleInit(): Promise<void>;
  $connect(): Promise<unknown>;
}
type SchemaGuardConstructor = new (options: {
  dataDir: string;
  execSchemaCommand: (command: string, options: SchemaCommandOptions) => void;
  readFileTrackerCount?: () => number;
}) => EnsureSchemaService;

// better-sqlite3 ships no type definitions — only this surface is used here.
interface TestSqliteHandle {
  exec: (sql: string) => void;
  prepare: (sql: string) => { get: () => unknown };
  close: () => void;
}

function openTestSqlite(file: string): TestSqliteHandle {
  const betterSqlite3 = createRequire(__filename)('better-sqlite3') as new (f: string) => TestSqliteHandle;
  return new betterSqlite3(file);
}

describe('PrismaService.ensureSchema (migrate deploy + dedup-state guard, C5)', () => {
  const SchemaGuardService = PrismaService as unknown as SchemaGuardConstructor;
  const SHRINK_MESSAGE = 'dedup state must not shrink (was 7, now 0)';

  let tmpDataDir: string;

  beforeEach(() => {
    tmpDataDir = mkdtempSync(join(tmpdir(), 'racochu-c5-'));
  });

  afterEach(() => {
    rmSync(tmpDataDir, { recursive: true, force: true });
  });

  function serviceWithSeams(options: {
    counts?: number[];
    execSchemaCommand?: (command: string, options: SchemaCommandOptions) => void;
  }) {
    const execSchemaCommand = jest.fn(
      options.execSchemaCommand ?? ((_command: string, _opts: SchemaCommandOptions) => undefined),
    );
    const scripted = [...(options.counts ?? [0, 0])];
    const readFileTrackerCount = jest.fn((): number => {
      const next = scripted.shift();
      if (next === undefined) {
        throw new Error('unexpected extra FileTracker count read beyond the scripted sequence');
      }
      return next;
    });
    const service = new SchemaGuardService({ dataDir: tmpDataDir, execSchemaCommand, readFileTrackerCount });
    return { service, execSchemaCommand, readFileTrackerCount };
  }

  it('runs the schema step via `prisma migrate deploy` and never via `db push`', () => {
    const { service, execSchemaCommand, readFileTrackerCount } = serviceWithSeams({ counts: [7, 7] });

    service.ensureSchema();

    expect(execSchemaCommand).toHaveBeenCalledTimes(1);
    const [command, execOptions] = execSchemaCommand.mock.calls[0];
    expect(command).toContain('prisma migrate deploy');
    expect(command).not.toContain('db push');
    expect(command).not.toContain('--accept-data-loss');
    expect(execOptions.cwd).toBe(findProjectRoot(__dirname));
    // Non-interactive deploy does not prompt — no consent-env plumbing allowed.
    expect(execOptions.env).toBeUndefined();
    // Count read happens around the schema step: before and after.
    expect(readFileTrackerCount).toHaveBeenCalledTimes(2);
  });

  it('passes when the dedup row count is stable across the schema step (7 → 7)', () => {
    const { service, execSchemaCommand } = serviceWithSeams({ counts: [7, 7] });

    expect(() => service.ensureSchema()).not.toThrow();
    expect(execSchemaCommand).toHaveBeenCalledTimes(1);
  });

  it('passes on a fresh/empty database (0 → 0)', () => {
    const { service, execSchemaCommand } = serviceWithSeams({ counts: [0, 0] });

    expect(() => service.ensureSchema()).not.toThrow();
    expect(execSchemaCommand).toHaveBeenCalledTimes(1);
  });

  it('aborts with the exact operator message when the dedup state shrinks (7 → 0)', () => {
    const { service } = serviceWithSeams({ counts: [7, 0] });

    let thrown: unknown;
    try {
      service.ensureSchema();
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as Error).message).toBe(SHRINK_MESSAGE);
  });

  it('still surfaces a failing migrate step as before, and never counts after it', () => {
    const migrationFailure = new Error('migrations failed');
    const { service, readFileTrackerCount } = serviceWithSeams({
      counts: [7], // only the pre-step read is expected — the post read must never happen
      execSchemaCommand: () => {
        throw migrationFailure;
      },
    });

    expect(() => service.ensureSchema()).toThrow(migrationFailure);
    expect(readFileTrackerCount).toHaveBeenCalledTimes(1);
  });

  it('aborts onModuleInit before any connect work when the guard trips', async () => {
    const { service } = serviceWithSeams({ counts: [7, 0] });
    const connect = jest.spyOn(service, '$connect').mockResolvedValue(undefined);

    await expect(service.onModuleInit()).rejects.toThrow(SHRINK_MESSAGE);
    expect(connect).not.toHaveBeenCalled();

    connect.mockRestore();
  });

  it('proceeds to connect when the guard passes', async () => {
    const { service } = serviceWithSeams({ counts: [0, 0] });
    const connect = jest.spyOn(service, '$connect').mockResolvedValue(undefined);

    await service.onModuleInit();
    expect(connect).toHaveBeenCalledTimes(1);

    connect.mockRestore();
  });

  it('real count source: treats a missing FileTracker table as 0 on a fresh database', () => {
    // No readFileTrackerCount injected — exercises the production default read
    // through the better-sqlite3 driver against an empty database.
    const execSchemaCommand = jest.fn();
    const service = new SchemaGuardService({ dataDir: tmpDataDir, execSchemaCommand });

    expect(() => service.ensureSchema()).not.toThrow();
    expect(execSchemaCommand).toHaveBeenCalledTimes(1);
  });

  it('real count source: detects an actual 3 → 0 shrink through the driver', () => {
    const dbPath = join(tmpDataDir, 'racochu.db');
    const seed = openTestSqlite(dbPath);
    seed.exec(
      `CREATE TABLE "FileTracker" ("id" INTEGER PRIMARY KEY, "filePath" TEXT NOT NULL);
       INSERT INTO "FileTracker" ("id", "filePath") VALUES (1, '/a'), (2, '/b'), (3, '/c');`,
    );
    seed.close();

    // The stubbed schema step wipes the rows — standing in for a destructive migrate.
    const execSchemaCommand = jest.fn((_command: string, _options: SchemaCommandOptions) => {
      const wipe = openTestSqlite(dbPath);
      wipe.exec('DELETE FROM "FileTracker"');
      wipe.close();
    });
    const service = new SchemaGuardService({ dataDir: tmpDataDir, execSchemaCommand });

    let thrown: unknown;
    try {
      service.ensureSchema();
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as Error).message).toBe('dedup state must not shrink (was 3, now 0)');
  });
});

describe('findProjectRoot', () => {
  let fixtureRoot: string;

  beforeEach(() => {
    fixtureRoot = mkdtempSync(join(tmpdir(), 'racochu-prisma-root-'));
    mkdirSync(join(fixtureRoot, 'prisma'), { recursive: true });
    writeFileSync(join(fixtureRoot, 'prisma', 'schema.prisma'), 'generator client { }\n');
  });

  afterEach(() => {
    rmSync(fixtureRoot, { recursive: true, force: true });
  });

  it('resolves the root from a shallow (src/dev) location', () => {
    const srcDir = join(fixtureRoot, 'src', 'infrastructure', 'prisma');

    expect(findProjectRoot(srcDir)).toBe(fixtureRoot);
  });

  it('resolves the root from a deep (dist) location', () => {
    const distDir = join(fixtureRoot, 'dist', 'src', 'infrastructure', 'prisma');

    expect(findProjectRoot(distDir)).toBe(fixtureRoot);
  });

  it('prefers the nearest directory containing prisma/schema.prisma', () => {
    // A nested project root must win over any schema living higher up.
    const nested = join(fixtureRoot, 'inner', 'app');
    mkdirSync(join(nested, 'prisma'), { recursive: true });
    writeFileSync(join(nested, 'prisma', 'schema.prisma'), 'generator client { }\n');
    const fromNested = join(nested, 'dist', 'src', 'infrastructure', 'prisma');

    expect(findProjectRoot(fromNested)).toBe(nested);
  });

  it('falls back to the legacy ../../../ resolution when no schema is found', () => {
    const isolated = join(tmpdir(), 'racochu-isolated', 'a', 'b', 'c');

    expect(findProjectRoot(isolated)).toBe(resolve(isolated, '../../../'));
  });
});
