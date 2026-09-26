import { ContentChunk } from '../../domain/content-chunk.entity';
import { BensyneRememberDto } from '../dto/bensyne-remember.dto';

/**
 * JSON-RPC 2.0 request for the rememberMemory tool.
 */
export interface RememberRequest {
  jsonrpc: '2.0';
  id: number;
  method: 'tools/call';
  params: {
    name: 'rememberMemory';
    arguments: Record<string, unknown>;
  };
}

/**
 * Serializes a ContentChunk entity into the exact JSON-RPC 2.0 request
 * that will be sent to the Bensyne server via tools/call (rememberMemory).
 *
 * This shared serializer ensures the clamp logic and the Bensyne client
 * use the same serialization, so the clamp measures the exact request body
 * that will be sent.
 */
export class RememberRequestSerializer {
  private nextRequestId = 1;

  /**
   * Build the rememberMemory request object for a chunk.
   *
   * @param chunk - The ContentChunk entity
   * @param options - Optional serialization options
   * @returns The JSON-RPC 2.0 request object
   */
  buildRequest(chunk: ContentChunk, options?: { forceReembed?: boolean }): RememberRequest {
    const payload = BensyneRememberDto.fromChunk(chunk);
    const argumentsPayload = options?.forceReembed ? { ...payload, force_reembed: true } : payload;

    return {
      jsonrpc: '2.0',
      id: this.nextRequestId++,
      method: 'tools/call',
      params: {
        name: 'rememberMemory',
        arguments: argumentsPayload as Record<string, unknown>,
      },
    };
  }

  /**
   * Serialize the request to a JSON string (for size measurement or direct sending).
   *
   * @param request - The request object to serialize
   * @returns JSON string
   */
  serialize(request: RememberRequest): string {
    return JSON.stringify(request, (_, value) =>
      typeof value === 'bigint' ? value.toString() : value,
    );
  }

  /**
   * Build and serialize a request in one step.
   *
   * @param chunk - The ContentChunk entity
   * @param options - Optional serialization options
   * @returns JSON string ready to send
   */
  buildAndSerialize(chunk: ContentChunk, options?: { forceReembed?: boolean }): string {
    const request = this.buildRequest(chunk, options);
    return this.serialize(request);
  }
}
