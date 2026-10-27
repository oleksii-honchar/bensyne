import '@/utils/mastra-rag.test-utils';

import { Test, TestingModule } from '@nestjs/testing';
import * as fsPromises from 'fs/promises';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { aSourceConfig } from '../../infrastructure/config/configuration.service.test-utils';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { aLogger } from '../../infrastructure/logging/logger.test-utils';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { aBensyneClientService } from '../../infrastructure/services/bensyne-client.test-utils';
import { ReprocessEdgesUseCase } from '../../use-cases/reprocess-edges.use-case';
import { Result } from '../../utils/result';
import { mockDirStats, mockDirent } from '../../utils/test-utils';
import { ReprocessEdgesService } from './reprocess-edges.service';

jest.mock('fs/promises');
const fsMock = fsPromises as jest.Mocked<typeof fsPromises>;

describe('ReprocessEdgesService', () => {
  let service: ReprocessEdgesService;
  let processEdgesUseCase: { execute: jest.Mock };
  let logger: ReturnType<typeof aLogger>;

  const okResult = { filesProcessed: 0, ghostEdgesFound: 0, edgesNeedUpdate: 0 };

  beforeEach(async () => {
    jest.clearAllMocks();
    fsMock.stat.mockReset();
    fsMock.readdir.mockReset();

    processEdgesUseCase = {
      execute: jest.fn().mockResolvedValue(Result.ok(okResult)),
    };
    logger = aLogger();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ReprocessEdgesService,
        { provide: ReprocessEdgesUseCase, useValue: processEdgesUseCase },
        { provide: BensyneClient, useValue: aBensyneClientService() },
        { provide: BasePinoLogger, useValue: logger },
      ],
    }).compile();

    service = module.get<ReprocessEdgesService>(ReprocessEdgesService);
  });

  const aMultiRootSource = (roots: string[]): WatchSourceConfig =>
    aSourceConfig({
      id: 'agent-persona_simple-session',
      path: roots[0],
      resolvedPaths: roots,
    });

  describe('multi-root enumeration over resolvedPaths (R1)', () => {
    it('passes the union of both roots files to the edge use-case, in declared order', async () => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('entry.md', false), mockDirent('10-flow', true)])
        .mockResolvedValueOnce([mockDirent('10-step.md', false)])
        .mockResolvedValueOnce([mockDirent('90-archive-latest.md', false)]);

      await service.reprocessSource('agent-persona_simple-session', [
        aMultiRootSource(['/edges/persona', '/edges/shared']),
      ]);

      expect(processEdgesUseCase.execute).toHaveBeenCalledTimes(1);
      const params = processEdgesUseCase.execute.mock.calls[0][0] as { filePaths: string[] };
      expect(params.filePaths).toEqual([
        '/edges/persona/entry.md',
        '/edges/persona/10-flow/10-step.md',
        '/edges/shared/90-archive-latest.md',
      ]);
    });

    it('keeps same-named files from different roots separate and de-dups identical absolute paths', async () => {
      fsMock.stat.mockResolvedValue(mockDirStats());

      // Name-clash: distinct absolute paths both survive.
      fsMock.readdir.mockResolvedValue([mockDirent('a.md', false)]);
      await service.reprocessSource('agent-persona_simple-session', [
        aMultiRootSource(['/clash/one', '/clash/two']),
      ]);
      const clashed = processEdgesUseCase.execute.mock.calls[0][0] as { filePaths: string[] };
      expect(clashed.filePaths).toEqual(['/clash/one/a.md', '/clash/two/a.md']);

      // Duplicate root declaration: enumerated once.
      processEdgesUseCase.execute.mockClear();
      fsMock.readdir.mockClear();
      await service.reprocessSource('agent-persona_simple-session', [
        aMultiRootSource(['/dup', '/dup/']),
      ]);
      const deduped = processEdgesUseCase.execute.mock.calls[0][0] as { filePaths: string[] };
      expect(deduped.filePaths).toEqual(['/dup/a.md']);
      expect(fsMock.readdir).toHaveBeenCalledTimes(1);
    });
  });

  describe('single-path enumeration (back-compat)', () => {
    it('enumerates exactly as before for single-path sources', async () => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('a.md', false), mockDirent('sub', true)])
        .mockResolvedValueOnce([mockDirent('b.md', false)]);

      await service.reprocessSource('agent-persona_simple-session', [
        aMultiRootSource(['/legacy/one-root']),
      ]);

      const params = processEdgesUseCase.execute.mock.calls[0][0] as { filePaths: string[] };
      expect(params.filePaths).toEqual(['/legacy/one-root/a.md', '/legacy/one-root/sub/b.md']);
    });
  });
});
