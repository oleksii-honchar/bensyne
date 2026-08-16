import { Test, TestingModule } from '@nestjs/testing';
import * as crypto from 'crypto';
import * as fs from 'fs/promises';
import { FileHasherService } from './file-hasher.service';

jest.mock('fs/promises');
const mockedFs = fs as jest.Mocked<typeof fs>;

describe('FileHasherService', () => {
  let service: FileHasherService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [FileHasherService],
    }).compile();

    service = module.get<FileHasherService>(FileHasherService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('compute', () => {
    it('returns SHA-256 hex string for file content', async () => {
      const content = Buffer.from('hello world');
      mockedFs.readFile.mockResolvedValue(content);

      const hash = await service.compute('/some/file.txt');

      const expected = crypto.createHash('sha256').update(content).digest('hex');
      expect(hash).toBe(expected);
      expect(mockedFs.readFile).toHaveBeenCalledWith('/some/file.txt');
    });

    it('produces the same hash for identical content (deterministic)', async () => {
      const content = Buffer.from('same content');
      mockedFs.readFile.mockResolvedValue(content);

      const hash1 = await service.compute('/file1.txt');
      const hash2 = await service.compute('/file2.txt');

      expect(hash1).toBe(hash2);
    });

    it('produces different hashes for different content', async () => {
      mockedFs.readFile
        .mockResolvedValueOnce(Buffer.from('content A'))
        .mockResolvedValueOnce(Buffer.from('content B'));

      const hashA = await service.compute('/fileA.txt');
      const hashB = await service.compute('/fileB.txt');

      expect(hashA).not.toBe(hashB);
    });

    it('produces a valid SHA-256 hash for an empty file', async () => {
      mockedFs.readFile.mockResolvedValue(Buffer.from(''));

      const hash = await service.compute('/empty.txt');

      const expected = crypto.createHash('sha256').digest('hex');
      expect(hash).toBe(expected);
      expect(hash).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    });

    it('throws when file read fails', async () => {
      mockedFs.readFile.mockRejectedValue(new Error('ENOENT'));

      await expect(service.compute('/missing.txt')).rejects.toThrow('ENOENT');
    });
  });
});
