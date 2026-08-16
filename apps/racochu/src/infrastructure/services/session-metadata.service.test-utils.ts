import { SessionMetadata } from '@/domain/session-metadata.type';
import { SessionMetadataService } from '@/infrastructure/services/session-metadata.service';
import { Result } from '@/utils/result';

export function aSessionMetadataService(
  metadata: SessionMetadata = {
    sessionId: 'ses_test123',
    createdAt: '2026-07-28T09:46:23Z',
    status: 'in-progress',
    phase: 'implementation',
    nextAgent: 'developer',
  },
): jest.Mocked<SessionMetadataService> {
  return {
    extract: jest.fn().mockResolvedValue(Result.ok(metadata)),
  } as unknown as jest.Mocked<SessionMetadataService>;
}
