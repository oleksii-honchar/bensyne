import { ContentChunk } from '@/domain/content-chunk.entity';
import { Result } from '@/utils/result';
import { MastraChunkingService } from './mastra-chunking.service';

export function aMastraChunkingService(chunks: ContentChunk[] = []): jest.Mocked<MastraChunkingService> {
  return {
    chunkFile: jest.fn().mockResolvedValue(Result.ok(chunks)),
  } as unknown as jest.Mocked<MastraChunkingService>;
}
