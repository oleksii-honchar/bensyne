import { aFileChunksInfo, aStoredChunkInfo } from '../../infrastructure/services/bensyne-client.test-utils';
import { isFileHealthy } from './file-health';

describe('isFileHealthy', () => {
  it('returns false for FILE_NOT_FOUND status', () => {
    const info = aFileChunksInfo({ status: 'FILE_NOT_FOUND', chunks: [] });
    expect(isFileHealthy(info)).toBe(false);
  });

  it('returns false when chunks exist but all are missing', () => {
    const info = aFileChunksInfo({
      chunks: [
        aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'missing' }),
        aStoredChunkInfo({ chunkIndex: 1, memoryStatus: 'missing' }),
      ],
    });
    expect(isFileHealthy(info)).toBe(false);
  });

  it('returns true when at least one chunk is present', () => {
    const info = aFileChunksInfo({
      chunks: [
        aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'missing' }),
        aStoredChunkInfo({ chunkIndex: 1, memoryStatus: 'present' }),
        aStoredChunkInfo({ chunkIndex: 2, memoryStatus: 'missing' }),
      ],
    });
    expect(isFileHealthy(info)).toBe(true);
  });

  it('returns true when all chunks are present', () => {
    const info = aFileChunksInfo({
      chunks: [
        aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'present' }),
        aStoredChunkInfo({ chunkIndex: 1, memoryStatus: 'present' }),
      ],
    });
    expect(isFileHealthy(info)).toBe(true);
  });

  it('returns false when no chunks exist', () => {
    const info = aFileChunksInfo({ chunks: [] });
    expect(isFileHealthy(info)).toBe(false);
  });
});
