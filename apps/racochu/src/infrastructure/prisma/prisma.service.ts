import { Injectable, OnModuleDestroy, OnModuleInit, Optional } from '@nestjs/common';
import { PrismaBetterSqlite3 } from '@prisma/adapter-better-sqlite3';
import { execSync } from 'child_process';
import fs from 'fs';
import { createRequire } from 'module';
import path from 'path';
import { PrismaClient } from '../../generated/prisma/client';

/**
 * Resolves the racochu project root — the directory containing prisma/schema.prisma —
 * by walking up from startDir. Works both in dev (src/...) and compiled (dist/src/...)
 * layouts, where a fixed relative depth would resolve to the wrong directory.
 */
export function findProjectRoot(startDir: string): string {
  let dir = startDir;
  for (;;) {
    if (fs.existsSync(path.join(dir, 'prisma', 'schema.prisma'))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      // No schema found up to the filesystem root — keep the legacy resolution
      // so failures surface where they always did.
      return path.resolve(startDir, '../../../');
    }
    dir = parent;
  }
}

/** Options passed to the schema step instead of the real `execSync` (test seam). */
export type SchemaCommandExecutor = (
  command: string,
  options: { cwd: string; stdio: 'inherit'; env?: Record<string, string | undefined> },
) => void;

/**
 * Seam overrides for the startup schema step (spec C5): the composed prisma
 * command execution and the FileTracker count source are injectable so the
 * migrate-deploy command and the dedup-shrink guard are unit-testable. All
 * defaults keep the production wiring unchanged.
 */
export interface PrismaServiceOptions {
  /** Directory holding racochu.db; defaults to <projectRoot>/data as before. */
  dataDir?: string;
  /** Runs the prisma schema command; defaults to execSync('npx prisma migrate deploy'). */
  execSchemaCommand?: SchemaCommandExecutor;
  /** Current FileTracker row count; defaults to a sync read through better-sqlite3. */
  readFileTrackerCount?: () => number;
}

/**
 * better-sqlite3 ships no type definitions; `@prisma/adapter-better-sqlite3`
 * keeps its driver handle private, so the startup count reads through the same
 * driver with the minimal surface actually used (no subprocess is spawned).
 */
interface BetterSqliteCountStatement {
  get: () => unknown;
}
interface BetterSqliteDatabaseHandle {
  prepare: (sql: string) => BetterSqliteCountStatement;
  close: () => void;
}
type BetterSqliteDriverConstructor = new (file: string) => BetterSqliteDatabaseHandle;

function openBetterSqlite(file: string): BetterSqliteDatabaseHandle {
  const driver = createRequire(__filename)('better-sqlite3') as BetterSqliteDriverConstructor;
  return new driver(file);
}

const DEFAULT_EXEC_SCHEMA_COMMAND: SchemaCommandExecutor = (command, options) => {
  execSync(command, options);
};

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  private readonly dbFilePath: string;
  private readonly execSchemaCommand: SchemaCommandExecutor;
  private readonly readFileTrackerCount: () => number;

  // @Optional: the seam object is a plain options bag, not a DI token — Nest
  // instantiates this provider with no argument and the defaults keep the
  // production wiring (see PrismaServiceOptions).
  constructor(@Optional() options: PrismaServiceOptions = {}) {
    const dataDir = options.dataDir ?? path.join(findProjectRoot(__dirname), 'data');
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
    const dbFilePath = path.join(dataDir, 'racochu.db');
    const adapter = new PrismaBetterSqlite3({ url: `file:${dbFilePath}` });
    super({ adapter });
    this.dbFilePath = dbFilePath;
    this.execSchemaCommand = options.execSchemaCommand ?? DEFAULT_EXEC_SCHEMA_COMMAND;
    this.readFileTrackerCount = options.readFileTrackerCount ?? (() => this.countFileTrackerRows());
  }

  async onModuleInit(): Promise<void> {
    this.ensureSchema();
    await this.$connect();
  }

  /**
   * Startup schema safety (spec C5 / DEC-A4): applies the committed migrations
   * NON-INTERACTIVELY via `prisma migrate deploy` — replacing the destructive
   * data-loss-tolerant schema push that could silently wipe the dedup state —
   * and fails loud if the FileTracker row count shrinks across the schema
   * step: a decrease means the schema step wiped local dedup state, so
   * startup aborts (throw = intentional fail-fast at the infra boundary,
   * consistent with the previous rethrow behavior) instead of entering a
   * silent full-re-ingest mode. A fresh/empty database (0 → 0, or missing
   * table = 0) is unaffected. Migrations deployment never prompts, so the
   * dangerous-action consent env plumbing was removed with it.
   */
  ensureSchema(): void {
    const projectRoot = findProjectRoot(__dirname);
    const before = this.readFileTrackerCount();
    try {
      this.execSchemaCommand('npx prisma migrate deploy', {
        cwd: projectRoot,
        stdio: 'inherit',
      });
    } catch (error) {
      console.error('Failed to apply Prisma migrations on startup', error);
      throw error;
    }
    const after = this.readFileTrackerCount();
    if (after < before) {
      throw new Error(`dedup state must not shrink (was ${before}, now ${after})`);
    }
  }

  async onModuleDestroy(): Promise<void> {
    await this.$disconnect();
  }

  /** Sync raw count through the driver the Prisma provider uses; a missing table means a fresh database (0). */
  private countFileTrackerRows(): number {
    const db = openBetterSqlite(this.dbFilePath);
    try {
      const row = db.prepare(`SELECT COUNT(*) AS "count" FROM "FileTracker"`).get() as {
        count: number | bigint;
      };
      return Number(row.count);
    } catch (error) {
      if (error instanceof Error && /no such table/i.test(error.message)) {
        return 0;
      }
      throw error;
    } finally {
      db.close();
    }
  }
}
