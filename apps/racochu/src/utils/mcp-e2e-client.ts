/**
 * Reusable MCP client helpers for E2E tests.
 * Uses Streamable HTTP transport (same as BensyneClient).
 */

import * as http from 'http';

export interface McpCallResult {
  response: Record<string, unknown>;
  sessionId?: string | null;
}

export interface McpClientConfig {
  hostname: string;
  port: number;
  path: string;
  token: string;
}

const defaultConfig: McpClientConfig = {
  hostname: 'localhost',
  port: 3001,
  path: '/mcp',
  token: 'e2e-test-token',
};

/**
 * Call an MCP tool via Streamable HTTP transport.
 */
export async function callMcpTool(
  method: string,
  params: Record<string, unknown>,
  sessionId?: string | null,
  config: McpClientConfig = defaultConfig,
): Promise<McpCallResult> {
  const id = Date.now();
  const body = JSON.stringify({ jsonrpc: '2.0', id, method, params });

  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        hostname: config.hostname,
        port: config.port,
        path: config.path,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json, text/event-stream',
          'Content-Length': Buffer.byteLength(body),
          Authorization: `Bearer ${config.token}`,
          ...(sessionId ? { 'Mcp-Session-Id': sessionId } : {}),
        },
      },
      res => {
        let data = '';
        res.on('data', (chunk: Buffer) => {
          data += chunk;
        });
        res.on('end', () => {
          const newSessionId = res.headers['mcp-session-id'] as string | undefined;

          // Handle SSE format
          const lines = data.split('\n');
          let jsonStr = '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              jsonStr += line.slice(6);
            }
          }

          try {
            const parsed = JSON.parse(jsonStr || data);
            resolve({
              response: parsed.result ?? {},
              sessionId: newSessionId ?? sessionId,
            });
          } catch {
            reject(new Error(`Failed to parse MCP response: ${data.slice(0, 500)}`));
          }
        });
      },
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

/**
 * Initialize an MCP session and return the session ID.
 */
export async function initializeMcpSession(config: McpClientConfig = defaultConfig): Promise<string | null> {
  const { sessionId } = await callMcpTool(
    'initialize',
    {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: { name: 'e2e-test-client', version: '1.0.0' },
    },
    undefined,
    config,
  );

  // Send initialized notification (fire-and-forget)
  const initNotifBody = JSON.stringify({
    jsonrpc: '2.0',
    method: 'notifications/initialized',
    params: {},
  });
  await new Promise<void>((resolve, reject) => {
    const req = http.request(
      {
        hostname: config.hostname,
        port: config.port,
        path: config.path,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(initNotifBody),
          Authorization: `Bearer ${config.token}`,
          ...(sessionId ? { 'Mcp-Session-Id': sessionId } : {}),
        },
      },
      res => {
        res.resume();
        res.on('end', resolve);
      },
    );
    req.on('error', reject);
    req.write(initNotifBody);
    req.end();
  });

  return sessionId ?? null;
}

/**
 * Call listMemoryBanks via MCP and return parsed memory banks.
 */
export async function listBanks(
  sessionId: string | null,
  config: McpClientConfig = defaultConfig,
): Promise<{ name: string; description?: string }[]> {
  const { response } = await callMcpTool(
    'tools/call',
    {
      name: 'listMemoryBanks',
      arguments: {},
    },
    sessionId,
    config,
  );

  // MCP wraps Mnemosyne JSON in content[0].text
  const contentItems = response.content;
  if (Array.isArray(contentItems) && contentItems.length > 0) {
    const textContent = contentItems.find(
      (c: unknown) => typeof c === 'object' && c != null && (c as { type?: string }).type === 'text',
    );
    if (textContent && typeof (textContent as { text?: string }).text === 'string') {
      const parsed = JSON.parse((textContent as { text: string }).text);
      return Array.isArray(parsed.banks) ? parsed.banks : [];
    }
  }

  // Fallback: direct result
  return Array.isArray(response.banks) ? response.banks : [];
}
