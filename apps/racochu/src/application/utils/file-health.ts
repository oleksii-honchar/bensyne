import { FileChunksInfo } from '../../infrastructure/services/bensyne-client.service';

/**
 * A file is "healthy" only when the bank has ≥1 live chunk (DEC-0086 memoryStatus).
 * Stub rows (file row + chunk rows, no memories) are NOT healthy.
 */
export function isFileHealthy(fileChunks: FileChunksInfo): boolean {
  return fileChunks.status !== 'FILE_NOT_FOUND' && fileChunks.chunks.some(c => c.memoryStatus === 'present');
}
