import { Injectable, OnApplicationBootstrap } from '@nestjs/common';
import * as http from 'http';
import * as https from 'https';
import { ContentChunk } from '../../domain/content-chunk.entity';
import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';
import { ConfigurationService } from '../config/configuration.service';
import { BensyneRecallResult } from './bensyne-recall-result.type';
import { BensyneRememberDto } from '../dto/bensyne-remember.dto';
import { BasePinoLogger } from '../logging/base-pino-logger';

/**
 * JSON-RPC 2.0 request sent to the MCP server.
 */
interface McpToolRequest {
  jsonrpc: '2.0';
  id: number;
  method: string;
  params: Record<string, unknown>;
}

/**
 * JSON-RPC 2.0 notification (fire-and-forget, no id).
 */
interface McpToolNotification {
  jsonrpc: '2.0';
  method: string;
  params?: Record<string, unknown>;
}

/**
 * JSON-RPC 2.0 response from the MCP server.
 * Bensyne results are wrapped by the MCP SDK in TextContent[].text.
 */
interface McpToolResponse {
  jsonrpc?: string;
  id?: number;
  result?: {
    // MCP SDK wraps Bensyne JSON in TextContent[].text
    content?: { type?: string; text?: string }[];
    // Direct result fields
    [key: string]: unknown;
  };
  error?: {
    code?: number;
    message?: string;
  };
}

/**
 * Streamable HTTP client for Bensyne MCP.
 *
 * Communicates with Bensyne via the MCP (Model Context Protocol) over
 * Streamable HTTP transport (POST to /mcp). Handles:
 * - MCP initialization handshake (initialize + notifications/initialized)
 * - Session tracking via Mcp-Session-Id header
 * - Tool calls: rememberMemory (ingest chunks), recallMemory (semantic search)
 * - Health checks via ping
 * - Retry logic with exponential backoff for remember operations
 */
@Injectable()
export class BensyneClient implements OnApplicationBootstrap {
  private logger!: BasePinoLogger;
  private baseUrl = '';
  private apiKey: string | undefined;
  private timeoutMs = 30000;
  private maxRetries = 3;
  private retryDelayMs = 1000;
  private mcpSessionId: string | null = null;
  private nextRequestId = 1;

  constructor(
    private readonly configService: ConfigurationService,
    logger: BasePinoLogger,
  ) {
    this.logger = logger;
  }

  private ensureConfigLoaded(): void {
    if (!this.baseUrl) {
      const mcpConfig = this.configService.getMcpConfig();
      this.baseUrl = mcpConfig.url.replace(/(\/messages\/?|\/mcp\/?)$/, '');
      this.apiKey = mcpConfig.apiKey;
      this.timeoutMs = mcpConfig.timeoutMs;
      this.maxRetries = mcpConfig.maxRetries;
      this.retryDelayMs = mcpConfig.retryDelayMs;
      this.logger = this.logger.child({ component: 'BensyneClient', mcpEndpoint: this.baseUrl });
    }
  }

  async onApplicationBootstrap(): Promise<void> {
    await this.initialize();
  }

  /**
   * Perform the MCP initialization handshake.
   *
   * Sends an initialize request to the MCP server, captures the session ID,
   * and sends the notifications/initialized signal. Called automatically on
   * application bootstrap; non-fatal failures are logged and retried on first use.
   *
   * @returns Result.ok on success or non-fatal failure (client remains usable)
   */
  async initialize(): Promise<Result<void>> {
    this.ensureConfigLoaded();
    this.logger.info(
      `Initializing Bensyne MCP client: baseUrl="${this.baseUrl}", timeoutMs=${this.timeoutMs}`,
    );

    try {
      // MCP protocol requires initialize handshake before tool calls
      const initResult = await this.initializeProtocol();
      if (!initResult.isOk()) {
        this.logger.warn(`MCP init failed, will retry on use: ${initResult.getFormattedErrors()}`);
        return Result.ok(undefined as unknown as void);
      }

      this.logger.info(
        `Bensyne MCP client initialized: baseUrl="${this.baseUrl}", mcpSessionId="${this.mcpSessionId}"`,
      );
      return Result.ok(undefined as unknown as void);
    } catch (error) {
      this.logger.error(
        `Failed to initialize Bensyne MCP client: ${error instanceof Error ? error.message : String(error)}`,
      );
      return Result.ok(undefined as unknown as void);
    }
  }

  /**
   * MCP initialize handshake — POST to /mcp with initialize method,
   * then POST notifications/initialized.
   */
  private async initializeProtocol(): Promise<Result<void>> {
    const request: McpToolRequest = {
      jsonrpc: '2.0',
      id: this.nextRequestId++,
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {},
        clientInfo: {
          name: 'racochu',
          version: '1.0.0',
        },
      },
    };

    try {
      const response = await this.sendRequest(request);

      // Store session ID if provided
      this.mcpSessionId = response._sessionId ?? null;

      if (response.error) {
        return Result.ko([new ErrorWithDetails(`MCP init error: ${response.error.message}`, 'McpInitError')]);
      }

      // Send initialized notification (fire-and-forget POST)
      await this.sendNotification({
        jsonrpc: '2.0',
        method: 'notifications/initialized',
        params: {},
      });

      return Result.ok(undefined as unknown as void);
    } catch (error) {
      return Result.ko([
        new ErrorWithDetails(error instanceof Error ? error.message : String(error), 'McpInitError'),
      ]);
    }
  }

  /**
   * Send a JSON-RPC notification via POST to /mcp (fire-and-forget).
   */
  private async sendNotification(notification: McpToolNotification): Promise<void> {
    const parsedUrl = new URL(this.baseUrl);
    const lib = parsedUrl.protocol === 'https:' ? https : http;
    const data = JSON.stringify(notification);

    const options = this.buildRequestOptions(parsedUrl, data);

    await new Promise<void>((resolve, reject) => {
      const req = lib.request(options, res => {
        res.on('data', () => {
          // drain response body
        });
        res.on('end', () => resolve());
      });

      req.on('error', reject);
      req.setTimeout(this.timeoutMs, () => {
        req.destroy();
        resolve();
      });

      req.write(data);
      req.end();
    });
  }

  /**
   * Ingest a content chunk via the rememberMemory MCP tool.
   *
   * Sends the chunk text and metadata to Mnemosyne for embedding and storage.
   * Retries up to maxRetries times on transient failures.
   *
   * @param chunk - The Chunk domain entity to store
   * @returns Result.ok with {memory_id, status} on successful storage; Result.ko after all retries exhausted
   */
  async remember(chunk: ContentChunk): Promise<Result<{ memory_id: string; status: string }>> {
    const payload = BensyneRememberDto.fromChunk(chunk);

    const request: McpToolRequest = {
      jsonrpc: '2.0',
      id: this.nextRequestId++,
      method: 'tools/call',
      params: {
        name: 'rememberMemory',
        arguments: payload,
      },
    };

    this.logger.debug(
      `Remembering chunk: id="${chunk.id}", index=${chunk.chunkIndex}, textLength=${chunk.text.length}`,
    );

    let lastError: Error | null = null;

    this.ensureConfigLoaded();
    for (let attempt = 1; attempt <= this.maxRetries; attempt++) {
      try {
        const response = await this.sendRequest(request);

        if (response.error) {
          const errMsg = `MCP error: ${response.error.message}`;
          this.logger.warn(`MCP tool error: chunkId="${chunk.id}", error="${errMsg}"`);
          lastError = new ErrorWithDetails(errMsg, 'McpToolError');
        } else {
          // Parse MCP response — result.content[0].text contains JSON from Mnemosyne
          const parsed = this.parseMcpResponse(response);
          const status = String(parsed.status ?? '');
          if (status === 'stored') {
            const memoryId = String(parsed.memory_id ?? '');
            this.logger.debug(
              `Chunk remembered; id="${chunk.id}", memoryId="${memoryId}", attempt=${attempt}`,
            );
            return Result.ok({ memory_id: memoryId, status });
          } else if (status === 'deduplicated') {
            const memoryId = String(parsed.memory_id ?? '');
            this.logger.debug(`Chunk deduplicated; id="${chunk.id}", existingMemoryId="${memoryId}"`);
            return Result.ok({ memory_id: memoryId, status });
          } else {
            const errMsg =
              typeof parsed.error === 'string'
                ? parsed.error
                : JSON.stringify(parsed) || 'Unexpected remember response';
            this.logger.warn(`Unexpected remember response: chunkId="${chunk.id}", response="${errMsg}"`);
            lastError = new ErrorWithDetails(errMsg, 'UnexpectedMcpResponse');
          }
        }
      } catch (error) {
        const errMsg = error instanceof Error ? error.message : String(error);
        this.logger.warn(
          `Request failed, retrying: chunkId="${chunk.id}", attempt=${attempt}/${this.maxRetries}, error="${errMsg}"`,
        );
        lastError = new ErrorWithDetails(errMsg, 'McpRequestError');
      }

      if (attempt < this.maxRetries) {
        await this.delay(this.retryDelayMs * attempt);
      }
    }

    this.logger.error(
      `Failed to remember chunk after ${this.maxRetries} retries: id="${chunk.id}", lastError="${lastError?.message}"`,
    );

    return Result.ko([lastError || new ErrorWithDetails('Failed to remember chunk', 'RememberChunkFailed')]);
  }

  /**
   * Forget (delete) a memory via the forgetMemory MCP tool.
   *
   * @param memoryId - Memory ID to delete
   * @param memoryBank - Memory bank where the memory resides
   * @returns Result.ok on success (response.status === "deleted"); Result.ko on error
   */
  async forget(memoryId: string, memoryBank: string): Promise<Result<void>> {
    this.ensureConfigLoaded();
    this.logger.debug(`Forgetting memory: memoryId="${memoryId}", memoryBank="${memoryBank}"`);

    const request: McpToolRequest = {
      jsonrpc: '2.0',
      id: this.nextRequestId++,
      method: 'tools/call',
      params: {
        name: 'forgetMemory',
        arguments: { memory_id: memoryId, memory_bank: memoryBank },
      },
    };

    try {
      const response = await this.sendRequest(request);

      if (response.error) {
        return Result.ko([new ErrorWithDetails(`MCP error: ${response.error.message}`, 'McpToolError')]);
      }

      // Parse MCP response — result.content[0].text contains JSON from Mnemosyne
      const parsed = this.parseMcpResponse(response);
      if (parsed.status === 'deleted') {
        this.logger.info(`Memory forgotten: memoryId="${memoryId}"`);
        return Result.ok(undefined as unknown as void);
      }
      if (parsed.status === 'not_found') {
        this.logger.debug(`Memory already absent: memoryId="${memoryId}"`);
        return Result.ok(undefined as unknown as void);
      }

      const errMsg =
        typeof parsed.error === 'string'
          ? parsed.error
          : JSON.stringify(parsed) || 'Unexpected forget response';
      this.logger.warn(`Unexpected forget response: memoryId="${memoryId}", response="${errMsg}"`);
      return Result.ko([new ErrorWithDetails(errMsg, 'UnexpectedMcpResponse')]);
    } catch (error) {
      this.logger.error(
        `Failed to forget memory: memoryId="${memoryId}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
      return Result.ko([
        new ErrorWithDetails(error instanceof Error ? error.message : String(error), 'ForgetMemoryError'),
      ]);
    }
  }

  /**
   * Register a memory bank with a description via the registerMemoryBank MCP tool.
   *
   * @param name - Memory bank name
   * @param description - Human-readable description of what this memory bank contains
   * @returns Result.ok on success (response.status === "registered"); Result.ko on error
   */
  async registerBank(name: string, description: string): Promise<Result<void>> {
    this.ensureConfigLoaded();
    this.logger.debug(`Registering memory bank: name="${name}", description="${description}"`);

    const request: McpToolRequest = {
      jsonrpc: '2.0',
      id: this.nextRequestId++,
      method: 'tools/call',
      params: {
        name: 'registerMemoryBank',
        arguments: { name, description },
      },
    };

    try {
      const response = await this.sendRequest(request);

      if (response.error) {
        return Result.ko([new ErrorWithDetails(`MCP error: ${response.error.message}`, 'McpToolError')]);
      }

      // Parse MCP response — result.content[0].text contains JSON from Mnemosyne
      const parsed = this.parseMcpResponse(response);
      if (parsed.status === 'registered') {
        this.logger.info(`Memory bank registered: name="${name}"`);
        return Result.ok(undefined as unknown as void);
      }

      const errMsg =
        typeof parsed.error === 'string'
          ? parsed.error
          : JSON.stringify(parsed) || 'Unexpected register_bank response';
      this.logger.warn(`Unexpected register_bank response: name="${name}", response="${errMsg}"`);
      return Result.ko([new ErrorWithDetails(errMsg, 'UnexpectedMcpResponse')]);
    } catch (error) {
      this.logger.error(
        `Failed to register memory bank: name="${name}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
      return Result.ko([
        new ErrorWithDetails(
          error instanceof Error ? error.message : String(error),
          'MemoryBankRegistrationError',
        ),
      ]);
    }
  }

  /**
   * Verify Mnemosyne server health via MCP ping.
   *
   * @returns Result.ok(true) if server responds, Result.ok(false) on error response, Result.ko on transport failure
   */
  async healthCheck(): Promise<Result<boolean>> {
    this.ensureConfigLoaded();
    this.logger.debug(`Health checking Bensyne MCP; baseUrl="${this.baseUrl}"`);

    try {
      const response = await this.sendRequest({
        jsonrpc: '2.0',
        id: this.nextRequestId++,
        method: 'ping',
        params: {},
      });

      const healthy = !response.error && response.result !== undefined;
      this.logger.debug('Health check result', { healthy });
      return Result.ok(healthy);
    } catch (error) {
      this.logger.debug(`Health check failed: ${error instanceof Error ? error.message : String(error)}`);
      return Result.ko([
        new ErrorWithDetails(error instanceof Error ? error.message : String(error), 'HealthCheckError'),
      ]);
    }
  }

  /**
   * Perform semantic search via the recallMemory MCP tool.
   *
   * Queries Mnemosyne for memories matching the query. Retries if empty results
   * are returned (to allow for eventual consistency after recent ingests).
   *
   * @param query - Search query string
   * @param maxRetries - Maximum retry attempts on empty results (default: 5)
   * @param retryDelayMs - Base delay between retries in ms (default: 1000)
   * @param memoryBank - Memory bank to search (default: 'default')
   * @returns Result.ok with array of recall results; each result carries the
   *          memory `content` plus, when bensyne adds it, an opaque
   *          `file_enrichment` block passed through untouched (S6 tolerance);
   *          Result.ko on error
   */
  async recall(
    query: string,
    maxRetries = 5,
    retryDelayMs = 1000,
    memoryBank = 'default',
  ): Promise<Result<BensyneRecallResult[]>> {
    this.ensureConfigLoaded();
    this.logger.debug(`Recalling memories; query="${query}", memoryBank="${memoryBank}"`);

    const request: McpToolRequest = {
      jsonrpc: '2.0',
      id: this.nextRequestId++,
      method: 'tools/call',
      params: {
        name: 'recallMemory',
        arguments: { query, limit: 20, memory_bank: memoryBank },
      },
    };

    try {
      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        const response = await this.sendRequest(request);

        if (response.error) {
          return Result.ko([new ErrorWithDetails(`MCP error: ${response.error.message}`, 'McpToolError')]);
        }

        // Parse MCP response — result.content[0].text contains JSON from Mnemosyne
        const parsed = this.parseMcpResponse(response);
        if (parsed.status === 'error') {
          const errMsg =
            (typeof parsed.message === 'string' ? parsed.message : JSON.stringify(parsed.message)) ||
            'Recall error';
          return Result.ko([new ErrorWithDetails(errMsg, 'RecallError')]);
        }

        // Tolerant additive mapping (S6): each result passes through its
        // `content` plus any bensyne-owned `file_enrichment` key untouched.
        // Results without the key map byte-identical to today's shape.
        const rawResults = parsed.results;
        const results: BensyneRecallResult[] = Array.isArray(rawResults)
          ? rawResults.flatMap((r): BensyneRecallResult[] => {
              if (typeof r !== 'object' || r === null) return [];
              const item = r as Record<string, unknown>;
              const content = item.content;
              if (typeof content !== 'string' || content.length === 0) return [];
              const result: BensyneRecallResult = { content };
              if ('file_enrichment' in item) {
                result.file_enrichment = item.file_enrichment ?? null;
              }
              return [result];
            })
          : [];

        if (results.length > 0) {
          this.logger.debug(`Recall returned ${results.length} results for query="${query}"`);
          return Result.ok(results);
        }

        if (attempt === maxRetries) {
          this.logger.debug(`Recall returned 0 results after ${maxRetries} attempts for query="${query}"`);
          return Result.ok([]);
        }

        this.logger.debug(`Recall returned empty, retrying: attempt=${attempt}/${maxRetries}`);
        await this.delay(retryDelayMs * attempt);
      }

      return Result.ok([]);
    } catch (error) {
      return Result.ko([
        new ErrorWithDetails(error instanceof Error ? error.message : String(error), 'RecallError'),
      ]);
    }
  }

  /**
   * Parse MCP SDK TextContent response.
   *
   * The Bensyne SDK wraps's JSON result in TextContent[].text.
   * This method extracts and parses that inner JSON, falling back to raw
   * response.result if no TextContent is present.
   *
   * @param response - Raw MCP tool response
   * @returns Parsed result object from Mnemosyne
   */
  private parseMcpResponse(response: McpToolResponse): Record<string, unknown> {
    const contentItems = response.result?.content;
    if (Array.isArray(contentItems) && contentItems.length > 0) {
      const textContent = contentItems.find(c => c?.type === 'text')?.text;
      if (textContent) {
        try {
          return JSON.parse(textContent);
        } catch {
          return { text: textContent };
        }
      }
    }

    // Fallback: return response.result directly
    return (response.result ?? {}) as Record<string, unknown>;
  }

  /**
   * Send a JSON-RPC request via Streamable HTTP POST to /mcp.
   *
   * Handles session tracking via Mcp-Session-Id header. Non-200 responses
   * and timeouts are rejected as errors.
   *
   * @param request - JSON-RPC 2.0 request object
   * @returns Parsed MCP response with optional session ID
   */
  private async sendRequest(
    request: McpToolRequest,
  ): Promise<McpToolResponse & { _sessionId?: string | null }> {
    this.ensureConfigLoaded();

    const parsedUrl = new URL(this.baseUrl);
    const lib = parsedUrl.protocol === 'https:' ? https : http;
    const data = JSON.stringify(request, (_, value) =>
      typeof value === 'bigint' ? value.toString() : value,
    );

    const options = this.buildRequestOptions(parsedUrl, data);

    return new Promise((resolve, reject) => {
      const req = lib.request(options, res => {
        let body = '';

        res.on('data', (chunk: Buffer) => {
          body += chunk;
        });

        res.on('end', () => {
          // Capture Mcp-Session-Id header if present
          const sessionId = res.headers['mcp-session-id'] as string | undefined;
          if (sessionId) {
            this.mcpSessionId = sessionId;
          }

          // Handle non-2xx responses
          if (res.statusCode !== 200) {
            const snippet = body.slice(0, 200).replace(/\n/g, ' ');
            reject(new ErrorWithDetails(`HTTP ${res.statusCode}: ${snippet}`, 'McpHttpError'));
            return;
          }

          // Determine if response is SSE or JSON
          const contentType = (res.headers['content-type'] as string | undefined) ?? '';
          const responseBody = this.parseResponse(body, contentType);

          // Parse JSON-RPC response from body
          try {
            const response = JSON.parse(responseBody) as McpToolResponse;
            resolve({ ...response, _sessionId: sessionId ?? null });
          } catch (error) {
            reject(
              new ErrorWithDetails(
                `Failed to parse response: ${error instanceof Error ? error.message : String(error)}`,
                'McpParseError',
              ),
            );
          }
        });
      });

      req.on('error', error => {
        reject(error instanceof Error ? error : new Error(String(error)));
      });

      req.setTimeout(this.timeoutMs, () => {
        req.destroy();
        reject(
          new ErrorWithDetails(`Request timeout after ${this.timeoutMs}ms (id=${request.id})`, 'McpTimeout'),
        );
      });

      req.write(data);
      req.end();
    });
  }

  /**
   * Parse response body — handles both JSON and SSE formats.
   *
   * Streamable HTTP uses SSE (`event: message\ndata: {...}`) underneath
   * even though the transport is HTTP. Extract JSON from `data:` lines
   * when SSE format is detected.
   *
   * @param body - Raw response body string
   * @param contentType - Content-Type header value
   * @returns Parsed JSON string to be consumed by JSON.parse()
   */
  private parseResponse(body: string, contentType: string): string {
    // If it's SSE, extract the JSON from data: lines
    if (contentType.includes('text/event-stream') || body.startsWith('event:')) {
      const lines = body.split('\n');
      let jsonFragments = '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          jsonFragments += line.slice(6);
        }
      }
      return jsonFragments || body;
    }
    return body;
  }

  /**
   * Build HTTP request options for Streamable HTTP /mcp endpoint.
   *
   * @param parsedUrl - Base URL of the MCP server
   * @param data - JSON-stringified request body
   * @returns http.RequestOptions with auth and session headers
   */
  private buildRequestOptions(parsedUrl: URL, data: string): http.RequestOptions {
    return {
      hostname: parsedUrl.hostname,
      port: parsedUrl.port,
      path: '/mcp',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json, text/event-stream',
        'Content-Length': Buffer.byteLength(data),
        ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {}),
        ...(this.mcpSessionId ? { 'Mcp-Session-Id': this.mcpSessionId } : {}),
      },
    };
  }

  /**
   * Clean up client resources.
   *
   * Clears the MCP session ID. Called during graceful shutdown.
   */
  async close(): Promise<void> {
    this.logger.info('Closing Bensyne MCP client');
    this.mcpSessionId = null;
    this.logger.info('Bensyne MCP client closed');
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
