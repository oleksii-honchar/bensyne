import { aBodyChunk } from '@/domain/content-chunk.entity.test-utils';
import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import { Test } from '@nestjs/testing';
import { MastraChunkingService } from './mastra-chunking.service';
import { aMastraChunkingService } from './mastra-chunking.service.test-utils';
import { VaultChunkingStrategy } from './vault-chunking.strategy';

/**
 * Regression guard for the DI wiring of VaultChunkingStrategy.
 *
 * The strategy is registered as a NestJS provider (app.module.ts) and selected
 * by StrategyRouter for `sourceType: vault`. It relies on constructor injection
 * for MastraChunkingService and BasePinoLogger. Without @Injectable(), Nest
 * instantiates it with `undefined` dependencies and chunkFile throws:
 *   "Cannot read properties of undefined (reading 'chunkFile')"
 *
 * This test resolves the strategy through the real Nest DI container and asserts
 * its dependencies are wired and that chunking a vault note works end-to-end.
 */
describe('VaultChunkingStrategy DI wiring (regression)', () => {
  it('resolves constructor dependencies via NestJS DI and chunks a vault note without throwing', async () => {
    const mastraChunkingService = aMastraChunkingService([aBodyChunk()]);
    const logger = aLogger();

    const moduleRef = await Test.createTestingModule({
      providers: [
        VaultChunkingStrategy,
        { provide: MastraChunkingService, useValue: mastraChunkingService },
        { provide: BasePinoLogger, useValue: logger },
      ],
    }).compile();

    const sut = moduleRef.get(VaultChunkingStrategy);

    // DI must have injected real, non-undefined dependencies (the original bug
    // class left these undefined, crashing inside chunkFile).
    expect(sut['mastraChunkingService']).toBeDefined();
    expect(sut['mastraChunkingService']).toBe(mastraChunkingService);
    expect(sut['logger']).toBeDefined();
    expect(sut['logger']).toBe(logger);

    // Behavior: chunking a simple vault note through the DI-injected strategy must
    // succeed (no throw, real chunks returned). No wikilinks/see_also → no fs access.
    const result = await sut.chunkFile(
      '---\ntype: decision\nid: DEC-0001\n---\nVault note body.\n',
      '/test/vault/decisions/0001-alpha.decision.md',
      'test-source',
      aWatchSourceConfig({
        id: 'test-source',
        path: '/test/vault',
        memoryBank: 'test-source',
        exclude: ['**/node_modules/**'],
        sourceType: 'vault',
      }),
    );

    expect(result.isOk()).toBe(true);
    expect(result.getValue().length).toBeGreaterThan(0);
  });
});
