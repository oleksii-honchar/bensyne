import { Injectable, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { PrismaBetterSqlite3 } from '@prisma/adapter-better-sqlite3';
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { PrismaClient } from '../../generated/prisma/client';

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  constructor() {
    const dataDir = path.resolve(__dirname, '../../../data');
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
    const projectRoot = path.resolve(__dirname, '../../../');
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
