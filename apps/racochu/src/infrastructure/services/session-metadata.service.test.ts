import { Test, TestingModule } from '@nestjs/testing';
import * as fs from 'fs/promises';
import * as yaml from 'js-yaml';
import { BasePinoLogger } from '../logging/base-pino-logger';
import { aLogger } from '../logging/logger.test-utils';
import { SessionMetadataService } from './session-metadata.service';

jest.mock('fs/promises');
jest.mock('js-yaml');
const mockedFs = fs as jest.Mocked<typeof fs>;
const mockedYaml = yaml as jest.Mocked<typeof yaml>;

describe('SessionMetadataService', () => {
  let service: SessionMetadataService;
  let logger: jest.Mocked<BasePinoLogger>;

  beforeEach(async () => {
    jest.useFakeTimers();
    logger = aLogger();

    const module: TestingModule = await Test.createTestingModule({
      providers: [SessionMetadataService, { provide: BasePinoLogger, useValue: logger }],
    }).compile();

    service = module.get<SessionMetadataService>(SessionMetadataService);
  });

  afterEach(() => {
    jest.clearAllMocks();
    jest.useRealTimers();
  });

  describe('extract', () => {
    const validFrontmatter = `---
sessionId: ses_test123
createdAt: "2026-07-28T09:46:23Z"
status: in-progress
phase: implementation
nextAgent: developer
---

# Some content
`;

    it('returns extracted metadata on successful parse', async () => {
      mockedFs.readFile.mockResolvedValue(validFrontmatter);
      mockedYaml.load.mockReturnValue({
        sessionId: 'ses_test123',
        createdAt: '2026-07-28T09:46:23Z',
        status: 'in-progress',
        phase: 'implementation',
        nextAgent: 'developer',
      });

      const result = await service.extract('/test/session/path');

      expect(result.isOk()).toBe(true);
      const metadata = result.getValue();
      expect(metadata.sessionId).toBe('ses_test123');
      expect(metadata.createdAt).toBe('2026-07-28T09:46:23Z');
      expect(metadata.status).toBe('in-progress');
      expect(metadata.phase).toBe('implementation');
      expect(metadata.nextAgent).toBe('developer');
      expect(mockedFs.readFile).toHaveBeenCalledWith('/test/session/path/session.md', 'utf-8');
    });

    it('returns cached metadata on subsequent call within TTL', async () => {
      mockedFs.readFile.mockResolvedValue(validFrontmatter);
      mockedYaml.load.mockReturnValue({
        sessionId: 'ses_test123',
        createdAt: '2026-07-28T09:46:23Z',
        status: 'in-progress',
        phase: 'implementation',
        nextAgent: 'developer',
      });

      await service.extract('/test/session/path');
      await service.extract('/test/session/path');

      expect(mockedFs.readFile).toHaveBeenCalledTimes(1);
    });

    it('re-reads file after TTL expires', async () => {
      mockedFs.readFile.mockResolvedValue(validFrontmatter);
      mockedYaml.load.mockReturnValue({
        sessionId: 'ses_test123',
        createdAt: '2026-07-28T09:46:23Z',
        status: 'in-progress',
        phase: 'implementation',
        nextAgent: 'developer',
      });

      await service.extract('/test/session/path');
      expect(mockedFs.readFile).toHaveBeenCalledTimes(1);

      // Advance time past 5-minute TTL
      jest.advanceTimersByTime(5 * 60 * 1000 + 1);

      await service.extract('/test/session/path');
      expect(mockedFs.readFile).toHaveBeenCalledTimes(2);
    });

    it('returns empty metadata on file not found (graceful degradation)', async () => {
      const enoentError = new Error('ENOENT: no such file or directory');
      (enoentError as NodeJS.ErrnoException).code = 'ENOENT';
      mockedFs.readFile.mockRejectedValue(enoentError);

      const result = await service.extract('/nonexistent/path');

      expect(result.isOk()).toBe(true);
      const metadata = result.getValue();
      expect(metadata.sessionId).toBe('');
      expect(metadata.createdAt).toBe('');
      expect(metadata.status).toBe('');
      expect(metadata.phase).toBe('');
      expect(metadata.nextAgent).toBe('');
    });

    it('returns empty metadata on YAML parse failure (graceful degradation)', async () => {
      mockedFs.readFile.mockResolvedValue(validFrontmatter);
      mockedYaml.load.mockImplementation(() => {
        throw new Error('YAML parse error');
      });

      const result = await service.extract('/test/session/path');

      expect(result.isOk()).toBe(true);
      const metadata = result.getValue();
      expect(metadata.sessionId).toBe('');
      expect(metadata.createdAt).toBe('');
      expect(metadata.status).toBe('');
      expect(metadata.phase).toBe('');
      expect(metadata.nextAgent).toBe('');
    });

    it('returns empty metadata when frontmatter is missing', async () => {
      mockedFs.readFile.mockResolvedValue('# No frontmatter here\njust content');
      mockedYaml.load.mockReturnValue({});

      const result = await service.extract('/test/session/path');

      expect(result.isOk()).toBe(true);
      const metadata = result.getValue();
      expect(metadata.sessionId).toBe('');
      expect(metadata.createdAt).toBe('');
      expect(metadata.status).toBe('');
      expect(metadata.phase).toBe('');
      expect(metadata.nextAgent).toBe('');
    });
  });
});
