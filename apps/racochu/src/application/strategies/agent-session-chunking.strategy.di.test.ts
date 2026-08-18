import { Test } from '@nestjs/testing';
import { aBodyChunk } from '@/domain/content-chunk.entity.test-utils';
import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import { SessionMetadataService } from '@/infrastructure/services/session-metadata.service';
import { aSessionMetadataService } from '@/infrastructure/services/session-metadata.service.test-utils';
import { AgentSessionChunkingStrategy } from './agent-session-chunking.strategy';
import { MastraChunkingService } from './mastra-chunking.service';
import { aMastraChunkingService } from './mastra-chunking.service.test-utils';

/**
 * Regression guard for the DI wiring of AgentSessionChunkingStrategy.
 *
 * The strategy is registered as a NestJS provider (app.module.ts). It relies on
 * constructor injection for SessionMetadataService, MastraChunkingService and
 * BasePinoLogger. Without @Injectable(), Nest instantiates it with `undefined`
 * dependencies and chunkFile throws:
 *   "Cannot read properties of undefined (reading 'extract')"
 *
 * This test resolves the strategy through the real Nest DI container and asserts
 * its dependencies are wired and that chunking works end-to-end.
 */
describe('AgentSessionChunkingStrategy DI wiring (regression)', () => {
  it('resolves constructor dependencies via NestJS DI and chunks a file without throwing', async () => {
    const sessionMetadataService = aSessionMetadataService();
    const mastraChunkingService = aMastraChunkingService([aBodyChunk()]);
    const logger = aLogger();

    const moduleRef = await Test.createTestingModule({
      providers: [
        AgentSessionChunkingStrategy,
        { provide: SessionMetadataService, useValue: sessionMetadataService },
        { provide: MastraChunkingService, useValue: mastraChunkingService },
        { provide: BasePinoLogger, useValue: logger },
      ],
    }).compile();

    const sut = moduleRef.get(AgentSessionChunkingStrategy);

    // DI must have injected real, non-undefined dependencies (the original bug
    // left these undefined, crashing inside chunkFile).
    expect(sut['sessionMetadataService']).toBeDefined();
    expect(sut['sessionMetadataService']).toBe(sessionMetadataService);
    expect(sut['mastraChunkingService']).toBeDefined();

    // Behavior: chunking through the DI-injected strategy must succeed (no throw,
    // real chunks returned) — this exercises this.sessionMetadataService.extract().
    const result = await sut.chunkFile(
      'Body content after frontmatter.',
      '/test/path/file.md',
      'test-source',
      aWatchSourceConfig({
        id: 'test-source',
        path: '/test/path',
        memoryBank: 'test-source',
        exclude: ['**/node_modules/**'],
        sourceType: 'agent-sessions',
      }),
    );

    expect(result.isOk()).toBe(true);
    expect(result.getValue().length).toBeGreaterThan(0);
    expect(sessionMetadataService.extract).toHaveBeenCalled();
  });
});
