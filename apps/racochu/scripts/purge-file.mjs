#!/usr/bin/env node
/**
 * Purge an already-ingested file from bensyne + the local racochu tracker DB.
 *
 * Plain Node ESM, no build step — consistent with the rest of the repo's
 * scripts. Reuses the SAME primitives the app uses, with zero new storage
 * logic:
 *
 *  1. bensyne side: MCP `forgetFile` tool (deletes the bensyne file row, its
 *     chunk rows, and the referenced memories) — the exact JSON-RPC wire
 *     format BensyneClient.forgetByFile uses (initialize handshake → tools/call
 *     with { file_path, memory_bank }).
 *  2. local side: Prisma `fileTracker.delete({ where: { filePath } })` — the
 *     exact call FileTrackerRepository.deleteByFilePath makes (cascade-deletes
 *     FileMemoryTracker rows; P2025 swallowed → idempotent).
 *
 * Config resolution mirrors the app bootstrap: APP_CONFIG_PATH env var, else
 * ~/.config/racochu.yaml; .env is loaded from CWD (like @nestjs/config) so
 * $VAR references in the YAML resolve the same way. The local DB is
 * apps/racochu/data/racochu.db via the same PrismaBetterSqlite3 adapter.
 *
 * Usage:
 *   node scripts/purge-file.mjs --file <path> --bank <bank>   # purge both sides
 *   node scripts/purge-file.mjs --file <path> --bank <bank> --check   # verify only
 *
 * Both steps are idempotent: a second run succeeds with no error
 * (forgetFile → already_deleted/FILE_NOT_FOUND no-op; local delete → P2025 no-op).
 */
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const MCP_BASE_STRIP_RE = /(\/messages\/?|\/mcp\/?)$/;
const ENV_VAR_PATTERN = /\$([A-Za-z_][A-Za-z0-9_]*)/g;
const OK_FORGET_STATUSES = new Set(['forgotten', 'already_deleted', 'FILE_NOT_FOUND']);export const USAGE = `purge-file.mjs — purge an already-ingested file from bensyne + local tracker DB

Usage:
  node scripts/purge-file.mjs --file <path> --bank <bank>
  node scripts/purge-file.mjs --file <path> --bank <bank> --check

Options:
  --file <path>       Absolute path of the file to purge
  --bank <bank>       Memory bank the file was ingested into
  --check             Verify current state only (no deletion)
  --help              Show this help
`;

/** Parse CLI args into { file, bank, check, help }. Throws on missing required args. */
export function parseArgs(args) {
  let file = null;
  let bank = null;
  let check = false;
  let help = false;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    switch (arg) {
      case '--file':
        file = args[++i] ?? null;
        break;
      case '--bank':
        bank = args[++i] ?? null;
        break;
      case '--check':
        check = true;
        break;
      case '--help':
      case '-h':
        help = true;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!help && !file) {
    throw new Error('Missing required --file <path>');
  }
  if (!help && !bank) {
    throw new Error('Missing required --bank <bank>');
  }

  return { file, bank, check, help };
}

/** Config path resolution — mirrors app.config.ts / CliArgsService. */
export function resolveConfigPath() {
  return process.env.APP_CONFIG_PATH ?? path.join(os.homedir(), '.config', 'racochu.yaml');
}

/** Load .env from CWD (KEY=VALUE lines) — mirrors @nestjs/config bootstrap. */
export function loadDotEnv(cwd = process.cwd()) {
  const envPath = path.join(cwd, '.env');
  if (!fs.existsSync(envPath)) return;
  const text = fs.readFileSync(envPath, 'utf-8');
  for (const line of text.split('\n')) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (!match) continue;
    const [, key, value] = match;
    if (process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

/** Recursively substitute $ENV_VAR references in string values (mirrors ConfigurationService). */
export function resolveEnvVars(obj) {
  if (typeof obj === 'string') {
    return obj.replace(ENV_VAR_PATTERN, (match, varName) => {
      const envValue = process.env[varName];
      return envValue !== undefined ? envValue : match;
    });
  }
  if (Array.isArray(obj)) {
    return obj.map(resolveEnvVars);
  }
  if (obj !== null && typeof obj === 'object') {
    const result = {};
    for (const [key, value] of Object.entries(obj)) {
      result[key] = resolveEnvVars(value);
    }
    return result;
  }
  return obj;
}

/** Load + resolve the racochu YAML config; returns { url, apiKey } from the mcp section. */
export async function loadMcpConfig(configFilePath = resolveConfigPath()) {
  // Lazy import keeps the scripts jest suite free of CJS-interop surprises.
  // js-yaml resolves to its native ESM build (dist/js-yaml.mjs) → named export.
  const { load: yamlLoad } = await import('js-yaml');
  const content = fs.readFileSync(configFilePath, 'utf-8');
  const parsed = yamlLoad(content);
  const resolved = resolveEnvVars(parsed);
  const mcp = resolved?.mcp ?? {};
  return {
    url: String(mcp.url ?? 'http://localhost:8765'),
    apiKey: typeof mcp.apiKey === 'string' && mcp.apiKey.length > 0 ? mcp.apiKey : undefined,
  };
}

/** Walk up from startDir to find the dir containing prisma/schema.prisma (mirrors PrismaService). */
export function findProjectRoot(startDir) {
  let dir = startDir;
  for (;;) {
    if (fs.existsSync(path.join(dir, 'prisma', 'schema.prisma'))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      return path.resolve(startDir, '../../../');
    }
    dir = parent;
  }
}

/**
 * Minimal Streamable-HTTP MCP client mirroring BensyneClient's wire format
 * (initialize handshake → notifications/initialized → tools/call). Returns a
 * client with `call(name, args)` → parsed tool result object, and `close()`.
 */
export async function createMcpClient(mcpConfig) {
  const baseUrl = mcpConfig.url.replace(MCP_BASE_STRIP_RE, '');
  const endpoint = `${baseUrl}/mcp`;
  let sessionId = null;
  let nextId = 1;

  async function post(body) {
    const headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
    };
    if (mcpConfig.apiKey) {
      headers.Authorization = `Bearer ${mcpConfig.apiKey}`;
    }
    if (sessionId) {
      headers['Mcp-Session-Id'] = sessionId;
    }
    const res = await fetch(endpoint, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });
    const sid = res.headers.get('mcp-session-id');
    if (sid) {
      sessionId = sid;
    }
    const text = await res.text();
    if (res.status !== 200 && res.status !== 202) {
      throw new Error(`MCP HTTP ${res.status}: ${text.slice(0, 200)}`);
    }
    if (!text || text.trim() === '') {
      return null;
    }
    // SSE responses (text/event-stream or `event:` prefixed) carry JSON in data: lines.
    let raw = text;
    const isSse = (res.headers.get('content-type') ?? '').includes('text/event-stream') || text.startsWith('event:');
    if (isSse) {
      const fragments = text
        .split('\n')
        .filter(line => line.startsWith('data: '))
        .map(line => line.slice(6));
      raw = fragments.join('') || text;
    }
    return JSON.parse(raw);
  }

  // MCP initialize handshake (BensyneClient.initializeProtocol).
  const init = await post({
    jsonrpc: '2.0',
    id: nextId++,
    method: 'initialize',
    params: {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: { name: 'racochu-purge-file', version: '1.0.0' },
    },
  });
  if (init?.error) {
    throw new Error(`MCP initialize error: ${init.error.message ?? JSON.stringify(init.error)}`);
  }
  await post({ jsonrpc: '2.0', method: 'notifications/initialized', params: {} });

  return {
    /**
     * Call an MCP tool. Returns the parsed tool result (Bensyne wraps its JSON
     * in result.content[0].text — same parse as BensyneClient.parseMcpResponse).
     */
    async call(name, args) {
      const response = await post({
        jsonrpc: '2.0',
        id: nextId++,
        method: 'tools/call',
        params: { name, arguments: args },
      });
      if (!response) {
        throw new Error(`MCP tool call returned no response: ${name}`);
      }
      if (response.error) {
        throw new Error(`MCP tool error: ${response.error.message ?? JSON.stringify(response.error)}`);
      }
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
      return response.result ?? {};
    },
    async close() {
      sessionId = null;
    },
  };
}

/**
 * Create a Prisma client over apps/racochu/data/racochu.db using the same
 * PrismaBetterSqlite3 adapter as PrismaService. Lazy import keeps the scripts
 * jest suite free of native bindings unless purge/check actually runs.
 */
export async function createPrismaClient(projectRoot = findProjectRoot(path.dirname(fileURLToPath(import.meta.url)))) {
  const { PrismaBetterSqlite3 } = await import('@prisma/adapter-better-sqlite3');
  const { PrismaClient } = await import('../src/generated/prisma/index.js');
  const adapter = new PrismaBetterSqlite3({ url: `file:${path.join(projectRoot, 'data', 'racochu.db')}` });
  return new PrismaClient({ adapter });
}

/** Read-only state check: bensyne getFileChunks + local tracker counts. */
export async function verifyState({ client, prisma, filePath, bank }) {
  let bensyne;
  try {
    const parsed = await client.call('getFileChunks', { file_path: filePath, memory_bank: bank });
    bensyne = {
      status: String(parsed.status ?? 'unknown'),
      chunks: Array.isArray(parsed.chunks) ? parsed.chunks.length : 0,
      fileId: parsed.file_id != null ? String(parsed.file_id) : undefined,
    };
  } catch (error) {
    bensyne = { status: 'ERROR', chunks: 0, error: error instanceof Error ? error.message : String(error) };
  }

  let local;
  try {
    const tracker = await prisma.fileTracker.findUnique({ where: { filePath } });
    const memories = tracker
      ? await prisma.fileMemoryTracker.count({ where: { fileTrackerId: tracker.id } })
      : 0;
    local = { trackers: tracker ? 1 : 0, memories };
  } catch (error) {
    local = { trackers: -1, memories: -1, error: error instanceof Error ? error.message : String(error) };
  }

  return { bensyne, local };
}

/**
 * Classify a forgetFile response as idempotent-success or unexpected.
 *
 * bensyne returns two shapes for "already gone":
 *  - `{ status: 'already_deleted' | 'FILE_NOT_FOUND' }` (JSON no-op contract
 *    BensyneClient.forgetByFile accepts), and
 *  - a tool error whose text contains `FILE_NOT_FOUND` (the real wire shape
 *    for a never-ingested file, e.g. after a prior purge).
 * Both mean the file is already absent — the desired end state — so both are
 * treated as success. Anything else is unexpected.
 */
export function classifyForgetResponse(parsed) {
  if (parsed && typeof parsed === 'object' && OK_FORGET_STATUSES.has(String(parsed.status))) {
    return true;
  }
  if (typeof parsed === 'object' && parsed !== null && typeof parsed.text === 'string') {
    return /FILE_NOT_FOUND/.test(parsed.text);
  }
  return false;
}

/** Purge both sides idempotently. Returns the forget status + final state. */
export async function purgeFile({ client, prisma, filePath, bank }) {
  const forget = await client.call('forgetFile', { file_path: filePath, memory_bank: bank });
  if (!classifyForgetResponse(forget)) {
    throw new Error(
      `forgetFile returned unexpected status "${String(forget.status ?? 'unknown')}": ${JSON.stringify(forget)}`,
    );
  }
  const status = String(forget.status ?? 'FILE_NOT_FOUND');

  // Local tracker delete — cascade deletes FileMemoryTracker rows; P2025 is
  // swallowed by the repository and mirrored here for idempotency.
  try {
    await prisma.fileTracker.delete({ where: { filePath } });
  } catch (error) {
    const code = error?.code;
    if (code !== 'P2025') {
      throw new Error(`Local tracker delete failed: ${error?.message ?? String(error)}`);
    }
  }

  return status;
}

export async function main(argv = process.argv.slice(2)) {
  let args;
  try {
    args = parseArgs(argv);
  } catch (error) {
    console.error(`[purge-file] ${error instanceof Error ? error.message : String(error)}`);
    console.error(USAGE);
    return 2;
  }

  if (args.help) {
    process.stdout.write(USAGE);
    return 0;
  }

  const filePath = args.file;
  const bank = args.bank;

  try {
    loadDotEnv();
    const mcpConfig = await loadMcpConfig();
    const client = await createMcpClient(mcpConfig);
    const prisma = await createPrismaClient();

    try {
      console.log(`[purge-file] file="${filePath}" bank="${bank}" mcp="${mcpConfig.url}"`);

      if (args.check) {
        const state = await verifyState({ client, prisma, filePath, bank });
        console.log(
          `[purge-file] check: bensyne=${JSON.stringify(state.bensyne)} local=${JSON.stringify(state.local)}`,
        );
        return 0;
      }

      const status = await purgeFile({ client, prisma, filePath, bank });
      console.log(`[purge-file] forgetFile status="${status}"`);

      const state = await verifyState({ client, prisma, filePath, bank });
      console.log(
        `[purge-file] post-purge: bensyne=${JSON.stringify(state.bensyne)} local=${JSON.stringify(state.local)}`,
      );

      const clean =
        state.bensyne.status === 'FILE_NOT_FOUND' &&
        state.bensyne.chunks === 0 &&
        state.local.trackers === 0 &&
        state.local.memories === 0;
      if (!clean) {
        console.error('[purge-file] post-purge verification FAILED — state not fully purged');
        return 1;
      }
      console.log('[purge-file] done: bensyne file, chunks, memories, and local tracker rows purged');
      return 0;
    } finally {
      await client.close();
      await prisma.$disconnect();
    }
  } catch (error) {
    console.error(`[purge-file] failed: ${error instanceof Error ? error.message : String(error)}`);
    return 1;
  }
}

const isMain =
  typeof process.argv[1] === 'string' && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  main().then(code => {
    process.exitCode = code;
  });
}
