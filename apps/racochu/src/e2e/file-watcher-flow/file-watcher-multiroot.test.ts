import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as yaml from 'js-yaml';
import * as os from 'os';
import * as path from 'path';
import { SOURCE_TYPES } from '../../infrastructure/config/source-types';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { callMcpTool, initializeMcpSession, listBanks } from '../../utils/mcp-e2e-client';
import { FileProcessingQueue } from '@/infrastructure/services/file-processing-queue.service';
import { createTestApplication } from '../main.test-application';

/**
 * ADR-8 Stage 1 — multi-root watch source (`paths`).
 *
 * One agent-persona source declaring TWO sibling roots (persona tree + shared
 * conformance tree) must land in ONE memory bank: one registration, files
 * ingested from both roots, and a plain-relative cross-root edge
 * (`../<sharedRootDir>/<node>.md`) present as a decision_next relation — all
 * with the real config loader (YAML → configurationSchema) and the real
 * watcher→chunker→MCP pipeline. Config-isolated like the registration suite.
 */

const PROCESSING_WAIT_MS = 20000; // debounce(500ms) + chunking + MCP ingestion
const BOOTSTRAP_WAIT_MS = 3000;
const UNIQUE_BANK = `e2e-mr-${Date.now()}`;

describe('[E2E] FileWatcher Multi-Root — paths fan-out into one bank (ADR-8)', () => {
  let app: INestApplication | null = null;
  let bensyneClient: BensyneClient | null = null;
  let processingQueue: FileProcessingQueue | null = null;
  let mcpSessionId: string | null = null;
  let personaRoot: string;
  let sharedRoot: string;
  let entryPath: string;
  let sharedNodePath: string;

  beforeAll(async () => {
    const watchDir = process.env.E2E_WATCH_DIR;
    if (!watchDir) {
      throw new Error('E2E_WATCH_DIR not set');
    }
    mcpSessionId = await initializeMcpSession();

    // Two sibling roots under the shared e2e temp root (names mirror the
    // real layout: agent-personas/<persona> + agent-personas/shared).
    const siblingBase = path.dirname(watchDir);
    personaRoot = path.join(siblingBase, `mr-${Date.now()}-persona`);
    sharedRoot = path.join(siblingBase, `mr-${Date.now()}-shared`);
    await fs.mkdir(path.join(personaRoot, '10-flow'), { recursive: true });
    await fs.mkdir(sharedRoot, { recursive: true });
    entryPath = path.join(personaRoot, '00-entry.md');
    sharedNodePath = path.join(sharedRoot, '90-archive-latest.md');

    // Dedicated config — note `paths:` (no `path:`), exercising the real
    // YAML → schema normalization.
    const multiRootConfigPath = path.join(
      await fs.mkdtemp(path.join(os.tmpdir(), 'rag-e2e-mr-')),
      'multiroot-config.yaml',
    );
    const config = {
      mcp: {
        url: 'http://localhost:3001',
        apiKey: 'e2e-test-token',
        timeoutMs: 30000,
        maxRetries: 3,
        retryDelayMs: 1000,
      },
      watchSources: [
        {
          id: `e2e-mr-src-${Date.now()}`,
          paths: [personaRoot, sharedRoot],
          sourceType: SOURCE_TYPES.AGENT_PERSONA,
          exclude: [],
          debounceMs: 500,
          memoryBank: UNIQUE_BANK,
          description: 'E2E multi-root persona source (ADR-8)',
        },
      ],
      chunking: {
        maxSizes: { agentSessions: 400, plainText: 450 },
        overlap: 50,
        hardCap: 600,
      },
      telemetry: { enabled: false },
    };
    await fs.writeFile(multiRootConfigPath, yaml.dump(config), 'utf-8');
    console.log(`[E2E-MultiRoot] Dedicated config written: ${multiRootConfigPath}`);

    app = await createTestApplication({
      overrides: [{ provide: 'CONFIG_FILE_PATH', useValue: multiRootConfigPath }],
    });
    await app.init();

    bensyneClient = app.get(BensyneClient);
    processingQueue = app.get(FileProcessingQueue);
    await new Promise(resolve => setTimeout(resolve, BOOTSTRAP_WAIT_MS));
    console.log('[E2E-MultiRoot] App bootstrapped with two-root source');
  }, 90000);

  afterAll(async () => {
    if (app) {
      const closePromise = app.close();
      let timeoutId: ReturnType<typeof setTimeout> | undefined;
      const timeoutPromise = new Promise(resolve => {
        timeoutId = setTimeout(resolve, 30000);
      });
      await Promise.race([closePromise, timeoutPromise]);
      if (timeoutId) clearTimeout(timeoutId);
    }
    for (const dir of [personaRoot, sharedRoot]) {
      await fs.rm(dir, { recursive: true, force: true }).catch(() => undefined);
    }
  });

  async function waitForIngestion(): Promise<void> {
    await new Promise(resolve => setTimeout(resolve, PROCESSING_WAIT_MS));
    await processingQueue!.waitForEmpty();
  }

  it('ingests node files from BOTH roots into the single memory bank', async () => {
    // Files land AFTER start (watch-add events; ignoreInitial skips nothing here).
    await fs.writeFile(
      entryPath,
      [
        '---',
        'id: 00-entry',
        'title: Entry',
        'entry: true',
        'edges:',
        '  - target: 10-flow/10-step.md',
        '    when: flow continues',
        `  - target: ../${path.basename(sharedRoot)}/90-archive-latest.md`,
        '    when: writing artifacts',
        '---',
        'Greet and assess. Multi-root ADR-8 canary entry.',
      ].join('\n'),
      'utf-8',
    );
    await fs.writeFile(
      path.join(personaRoot, '10-flow/10-step.md'),
      '---\nid: 10-step\ntitle: Step\n---\nDo the step.',
      'utf-8',
    );
    await fs.writeFile(
      sharedNodePath,
      '---\nid: 90-archive-latest\ntitle: Archive latest\nentry: false\n---\nArchive before writing. Shared conformance canary.',
      'utf-8',
    );
    console.log('[E2E-MultiRoot] Dropped node files into both roots');

    await waitForIngestion();

    // One bank registration: the unique bank exists exactly once in the registry.
    const banks = await listBanks(mcpSessionId);
    const matched = banks.filter(bank => bank.name === UNIQUE_BANK);
    expect(matched).toHaveLength(1);
    expect(matched[0].description).toBe('E2E multi-root persona source (ADR-8)');

    // Handles ingested from BOTH roots: bank-scoped file rows exist for each.
    const entryChunks = await bensyneClient!.getFileChunks(entryPath, UNIQUE_BANK);
    expect(entryChunks.isOk()).toBe(true);
    expect(entryChunks.getValue().status).toBe('present');
    expect(entryChunks.getValue().totalChunks).toBeGreaterThan(0);

    const sharedChunks = await bensyneClient!.getFileChunks(sharedNodePath, UNIQUE_BANK);
    expect(sharedChunks.isOk()).toBe(true);
    expect(sharedChunks.getValue().status).toBe('present');
    expect(sharedChunks.getValue().totalChunks).toBeGreaterThan(0);

    const localChunks = await bensyneClient!.getFileChunks(
      path.join(personaRoot, '10-flow/10-step.md'),
      UNIQUE_BANK,
    );
    expect(localChunks.isOk()).toBe(true);
    expect(localChunks.getValue().status).toBe('present');
  }, 120000);

  it('exposes the plain-relative cross-root edge as a decision_next relation in the merged index', async () => {
    // Graph proof over the SAME bank view the persona tools use: expanding the
    // entry node must return the shared-root node despite it living in another
    // watch root — plain-relative targets need no resolver branch (ADR-8).
    const personaHandle = `${path.basename(personaRoot)}/00-entry.md`;
    const sharedHandle = `${path.basename(sharedRoot)}/90-archive-latest.md`;

    const { response, sessionId } = await callMcpTool(
      'tools/call',
      {
        name: 'expandFileRelations',
        arguments: { memory_bank: UNIQUE_BANK, path_handle: personaHandle },
      },
      mcpSessionId,
    );
    mcpSessionId = sessionId ?? mcpSessionId;

    const content = (response as { content?: { type: string; text?: string }[] }).content ?? [];
    const text = content.find(item => item.type === 'text')?.text ?? '';
    let payload: unknown = null;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
    const related =
      payload !== null && typeof payload === 'object'
        ? ((payload as { related_files?: { file?: { path_handle?: string }; relation_type?: string }[] })
            .related_files ?? [])
        : [];

    expect(
      related.some(
        item =>
          item.file?.path_handle === sharedHandle && item.relation_type === 'decision_next',
      ),
    ).toBe(true);
  }, 60000);

  it('entry-node election is unaffected by the second root (getPersonaEntryNode)', async () => {
    // The bank's entry node must still be the persona root's 00-entry even
    // though a second root was ingested into the same bank (no shared-root
    // file carries entry: true).
    const personaHandle = `${path.basename(personaRoot)}/00-entry.md`;

    const { response, sessionId } = await callMcpTool(
      'tools/call',
      {
        name: 'getPersonaEntryNode',
        arguments: { memory_bank: UNIQUE_BANK },
      },
      mcpSessionId,
    );
    mcpSessionId = sessionId ?? mcpSessionId;

    const content = (response as { content?: { type: string; text?: string }[] }).content ?? [];
    const text = content.find(item => item.type === 'text')?.text ?? '';
    let payload: { title?: string; path_handle?: string; tags?: string[] } | null = null;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }

    expect(payload).not.toBeNull();
    expect(payload!.title).toBe('Entry');
    expect(payload!.path_handle).toBe(personaHandle);
    expect(payload!.tags).toEqual(['persona-node', '00-entry']);
  }, 60000);
});
