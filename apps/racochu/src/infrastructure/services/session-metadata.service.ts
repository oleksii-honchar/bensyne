import { SessionMetadata } from '@/domain/session-metadata.type';
import { Result } from '@/utils/result';
import { Injectable } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as yaml from 'js-yaml';
import * as path from 'path';
import { BasePinoLogger } from '../logging/base-pino-logger';

const FRONTMATTER_REGEX = /^---\n([\s\S]*?)\n---\n?/;
const CACHE_TTL_MS = 5 * 60 * 1000;

const emptyMetadata = (): SessionMetadata => ({
  sessionId: '',
  createdAt: '',
  status: '',
  phase: '',
  nextAgent: '',
});

interface CacheEntry {
  metadata: SessionMetadata;
  timestamp: number;
}

@Injectable()
export class SessionMetadataService {
  private readonly logger: BasePinoLogger;
  private readonly cache = new Map<string, CacheEntry>();

  constructor(logger: BasePinoLogger) {
    this.logger = logger.child({ component: 'SessionMetadataService' });
  }

  async extract(sessionPath: string): Promise<Result<SessionMetadata>> {
    const cached = this.cache.get(sessionPath);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return Result.ok(cached.metadata);
    }

    const metadata = await this.readAndParse(sessionPath);
    this.cache.set(sessionPath, { metadata, timestamp: Date.now() });
    return Result.ok(metadata);
  }

  private async readAndParse(sessionPath: string): Promise<SessionMetadata> {
    try {
      const filePath = path.join(sessionPath, 'session.md');
      const content = await fs.readFile(filePath, 'utf-8');

      const match = FRONTMATTER_REGEX.exec(content);
      if (!match) {
        this.logger.warn(`No frontmatter found in session.md; path="${filePath}"`);
        return emptyMetadata();
      }

      const parsed = yaml.load(match[1]) as Record<string, unknown> | null;
      if (!parsed || typeof parsed !== 'object') {
        this.logger.warn(`Invalid frontmatter in session.md; path="${filePath}"`);
        return emptyMetadata();
      }

      return {
        sessionId: typeof parsed.sessionId === 'string' ? parsed.sessionId : '',
        createdAt: typeof parsed.createdAt === 'string' ? parsed.createdAt : '',
        status: typeof parsed.status === 'string' ? parsed.status : '',
        phase: typeof parsed.phase === 'string' ? parsed.phase : '',
        nextAgent: typeof parsed.nextAgent === 'string' ? parsed.nextAgent : '',
      };
    } catch (error) {
      if (error instanceof Error && 'code' in error && (error as { code: string }).code === 'ENOENT') {
        this.logger.warn(`session.md not found; path="${sessionPath}"`);
      } else {
        this.logger.warn(
          `Failed to parse session metadata: ${(error as Error).message}; path="${sessionPath}"`,
        );
      }
      return emptyMetadata();
    }
  }
}
