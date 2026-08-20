import { Injectable, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { PrismaBetterSqlite3 } from '@prisma/adapter-better-sqlite3';
import { execSync } from 'child_process';
import fs from 'fs';
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

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  constructor() {
    const dataDir = path.join(findProjectRoot(__dirname), 'data');
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
    const adapter = new PrismaBetterSqlite3({ url: `file:${path.join(dataDir, 'racochu.db')}` });
    super({ adapter });
  }

  async onModuleInit(): Promise<void> {
    this.ensureSchema();
    await this.$connect();
  }

  private ensureSchema(): void {
    const projectRoot = findProjectRoot(__dirname);
    try {
      execSync('npx prisma db push --accept-data-loss', {
        cwd: projectRoot,
        env: { ...process.env, PRISMA_USER_CONSENT_FOR_DANGEROUS_AI_ACTION: 'yes' },
        stdio: 'inherit',
      });
    } catch (error) {
      console.error('Failed to push Prisma schema on startup', error);
      throw error;
    }
  }

  async onModuleDestroy(): Promise<void> {
    await this.$disconnect();
  }
}
