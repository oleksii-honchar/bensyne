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
      await service.reprocessSource('agent-persona_simple-session', [aMultiRootSource(['/dup', '/dup/'])]);
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

      await service.reprocessSource('agent-persona_simple-session', [aMultiRootSource(['/legacy/one-root'])]);

      const params = processEdgesUseCase.execute.mock.calls[0][0] as { filePaths: string[] };
      expect(params.filePaths).toEqual(['/legacy/one-root/a.md', '/legacy/one-root/sub/b.md']);
    });
  });

  describe("scope filter (EP3 alignment — ADR-3: implement the stub's documented intent)", () => {
    // Archaeology: the exclude block in scanDirectory was born EMPTY in
    // be40a0f with the comment "Skip excluded directories using the shared
    // glob matcher" — the intent was documented, the behavior never was
    // (EP3 emitted EVERY file under the roots). ADR-3 implements that
    // intent in the exact shape of EP2 (spec §5): descent guard stays
    // exclude-only (invariant I2), file emission uses isPathInScope.
    //
    // Fixture builder: aSourceConfig never sets `include` (opt-in,
    // never-defaulted field — Task 2 contract), so an include-carrying
    // source is built locally by layering the optional field onto the
    // builder output. Every case pins exclude explicitly: these tests
    // control the full effective scope, no random builder defaults involved.
    const aScopedSource = (
      rootPath: string,
      include: string[],
      exclude: string[] = [],
    ): WatchSourceConfig => ({
      ...aSourceConfig({ id: 'agent-persona_simple-session', path: rootPath, exclude }),
      include,
    });

    const emittedPaths = (): string[] => {
      const call = processEdgesUseCase.execute.mock.calls[0];
      return call ? (call[0] as { filePaths: string[] }).filePaths : [];
    };

    it("does not emit files under an excluded directory and never descends it (the stub's own be40a0f intent) (E3-1)", async () => {
      // The behavior the stub's comment promised since birth: an
      // exclude-matched tree is skipped at the descent branch — its files
      // never reach the edge use-case. Include absent here: pure stub intent.
      const source = aSourceConfig({
        id: 'agent-persona_simple-session',
        path: '/edges-scope/single',
        exclude: ['**/tool-responses/**'],
      });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('keep.md', false), mockDirent('tool-responses', true)])
        .mockResolvedValueOnce([mockDirent('payload.md', false)]);

      await service.reprocessSource('agent-persona_simple-session', [source]);

      expect(emittedPaths()).toEqual(['/edges-scope/single/keep.md']);
      expect(fsMock.readdir).not.toHaveBeenCalledWith('/edges-scope/single/tool-responses', {
        withFileTypes: true,
      });
    });

    it('with include ["**/*.md"], emits ONLY .md files — other extensions never reach edge reprocessing (E3-2)', async () => {
      const source = aScopedSource('/edges-scope/single', ['**/*.md']);

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([
        mockDirent('notes.txt', false),
        mockDirent('report.md', false),
        mockDirent('data.json', false),
      ]);

      await service.reprocessSource('agent-persona_simple-session', [source]);

      expect(emittedPaths()).toEqual(['/edges-scope/single/report.md']);
    });

    it('an exclude match wins over a matching include pattern (E3-3)', async () => {
      // Spec §4 truth table row: match ∩ excluded → skip (exclude wins).
      // File-level conflict: draft.md MATCHES the include list and is also
      // exclude-matched; only the composed scope check resolves it.
      const source = aScopedSource('/edges-scope/single', ['**/*.md'], ['**/draft.md']);

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([
        mockDirent('report.md', false), // in scope (included, not excluded)
        mockDirent('draft.md', false), // include-match ∧ exclude-match → excluded wins
        mockDirent('notes.txt', false), // no include match → filtered
      ]);

      await service.reprocessSource('agent-persona_simple-session', [source]);

      expect(emittedPaths()).toEqual(['/edges-scope/single/report.md']);
    });

    it('include-absent emits exactly the exclude-complement — excluded paths are now skipped at EP3 (intended change per ADR-3) (E3-4)', async () => {
      // This is the DELIBERATE behavior change of this task: today EP3 emits
      // exclude-matched files too (empty stub); after the alignment fix the
      // emitted set is the exclude-complement — same semantics as EP2 for
      // include-absent sources (spec §5, success criterion 2).
      const source = aSourceConfig({
        id: 'agent-persona_simple-session',
        path: '/edges-scope/single',
        exclude: ['**/node_modules/**'],
      });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([
          mockDirent('node_modules', true), // excluded — never descended
          mockDirent('a.md', false),
          mockDirent('b.txt', false),
        ])
        .mockResolvedValueOnce([mockDirent('junk.log', false)]);

      await service.reprocessSource('agent-persona_simple-session', [source]);

      expect(emittedPaths().sort()).toEqual(['/edges-scope/single/a.md', '/edges-scope/single/b.txt']);
      expect(fsMock.readdir).not.toHaveBeenCalledWith('/edges-scope/single/node_modules', {
        withFileTypes: true,
      });
    });

    it('descends a directory matching NO include pattern and emits the md inside it; sibling txt still filtered (I2) (E3-5)', async () => {
      // The §5 hazard at this EP: extension include patterns never match
      // directory paths, so include must NOT prune descent (descent is
      // exclude-only). The file inside the non-matching directory is scoped
      // by its own path at emission time.
      const source = aScopedSource('/edges-scope/single', ['**/*.md']);

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('session-archive-2026', true)]) // no include pattern names this dir
        .mockResolvedValueOnce([mockDirent('inner.md', false), mockDirent('inner.txt', false)]);

      await service.reprocessSource('agent-persona_simple-session', [source]);

      expect(fsMock.readdir).toHaveBeenCalledWith('/edges-scope/single/session-archive-2026', {
        withFileTypes: true,
      });
      expect(emittedPaths()).toEqual(['/edges-scope/single/session-archive-2026/inner.md']);
    });

    it('include: [] is include-neutral — same emitted set as absent (truth-table row absent/[]) (parity lock)', async () => {
      // By-design parity lock (mirrors the EP2 lock): green before AND after
      // the wiring; it pins the empty-list row of the spec §4 truth table.
      const source = aScopedSource('/edges-scope/single', []);

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('a.md', false), mockDirent('b.txt', false)]);

      await service.reprocessSource('agent-persona_simple-session', [source]);

      expect(emittedPaths().sort()).toEqual(['/edges-scope/single/a.md', '/edges-scope/single/b.txt']);
    });
  });
});
