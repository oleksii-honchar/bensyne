import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as yaml from 'js-yaml';
import * as os from 'os';
import * as path from 'path';
import { SOURCE_STRATEGIES } from '../../infrastructure/config/source-strategies';
import { initializeMcpSession, listBanks } from '../../utils/mcp-e2e-client';
import { createTestApplication } from '../main.test-application';

const BOOTSTRAP_WAIT_MS = 5000; // Time for FileWatcherService.registerBanks() to complete

// Unique bank name per test run — ensures the "absent before bootstrap" assertion
// holds regardless of suite execution order (all E2E suites share one Mnemosyne
// container, so a shared bank name like e2e-test-ns may already be registered by
// an earlier suite).
const UNIQUE_BANK = `e2e-reg-${Date.now()}`;

describe('[E2E] Memory Bank Registration — racochu registers memory banks on bootstrap', () => {
  let app: INestApplication | null = null;
  let mcpSessionId: string | null = null;

  // Step 1: BEFORE Racochu starts — verify the unique bank is absent
  beforeAll(async () => {
    console.log('[E2E-MemoryBankRegistration] Initializing MCP session before app bootstrap...');
    mcpSessionId = await initializeMcpSession();

    // List memory banks BEFORE Racochu starts
    console.log('[E2E-MemoryBankRegistration] Listing memory banks BEFORE app bootstrap...');
    const banksBefore = await listBanks(mcpSessionId);
    console.log(`[E2E-MemoryBankRegistration] Memory banks before bootstrap: ${JSON.stringify(banksBefore)}`);

    // Verify default memory bank exists with hardcoded description
    const defaultBankBefore = banksBefore.find(bank => bank.name === 'default');
    expect(defaultBankBefore).toBeDefined();
    expect(defaultBankBefore!.description).toBe(
      'Default personal memory — general conversation context, preferences, and facts',
    );
    console.log('[E2E-MemoryBankRegistration] Default memory bank confirmed before bootstrap');

    // Verify the unique test bank does NOT exist before bootstrap
    const testBankBefore = banksBefore.find(bank => bank.name === UNIQUE_BANK);
    expect(testBankBefore).toBeUndefined();
    console.log('[E2E-MemoryBankRegistration] Unique test bank confirmed absent before bootstrap');

    // Write a dedicated config for this suite with a unique bank name, so the
    // app registers UNIQUE_BANK (never a name another suite already registered).
    const uniqueConfigPath = path.join(
      await fs.mkdtemp(path.join(os.tmpdir(), 'rag-e2e-reg-')),
      'memory-bank-reg-config.yaml',
    );
    const watchDir = process.env.E2E_WATCH_DIR;
    if (!watchDir) {
      throw new Error('E2E_WATCH_DIR not set');
    }
    const uniqueConfig = {
      mcp: {
        url: 'http://localhost:3001',
        apiKey: 'e2e-test-token',
        timeoutMs: 30000,
        maxRetries: 3,
        retryDelayMs: 1000,
      },
      watchSources: [
        {
          id: 'e2e-memory-bank-reg-source',
          path: watchDir,
          exclude: [],
          debounceMs: 500,
          memoryBank: UNIQUE_BANK,
          description: 'E2E memory bank registration verification',
        },
      ],
      chunking: {
        strategy: SOURCE_STRATEGIES.CONTENT_AWARE,
        maxSizes: {
          agentSessions: 400,
          obsidianNotes: 500,
          codeFiles: 400,
          configuration: 'per-key',
          plainText: 450,
        },
        overlap: 50,
        hardCap: 600,
      },
      enhancement: {
        maxCharacters: {
          prose: 2000,
          code: 3000,
          configuration: 1000,
          documentation: 2000,
        },
      },
      telemetry: {
        enabled: false,
      },
    };
    await fs.writeFile(uniqueConfigPath, yaml.dump(uniqueConfig), 'utf-8');
    console.log(`[E2E-MemoryBankRegistration] Dedicated config written: ${uniqueConfigPath}`);

    // Start Racochu with the dedicated config (unique bank)
    console.log('[E2E-MemoryBankRegistration] Starting racochu app...');
    app = await createTestApplication({
      overrides: [{ provide: 'CONFIG_FILE_PATH', useValue: uniqueConfigPath }],
    });
    await app.init();

    // Wait for FileWatcherService.onApplicationBootstrap to complete memory bank registration
    await new Promise(resolve => setTimeout(resolve, BOOTSTRAP_WAIT_MS));
    console.log('[E2E-MemoryBankRegistration] App bootstrapped, memory bank registration should be complete');
  }, 90000);

  afterAll(async () => {
    if (app) {
      const closePromise = app.close();
      let timeoutId: ReturnType<typeof setTimeout> | undefined;
      const timeoutPromise = new Promise(resolve => {
        timeoutId = setTimeout(resolve, 30000);
      });
      await Promise.race([closePromise, timeoutPromise]);
      // Clear the fallback timer — otherwise Jest sees a pending open handle
      if (timeoutId) clearTimeout(timeoutId);
    }
  });

  // Step 2: AFTER bootstrap — verify the unique watch source memory bank appears with description
  it('should have registered the unique memory bank with description after bootstrap', async () => {
    console.log('[E2E-MemoryBankRegistration] Listing memory banks AFTER app bootstrap...');
    const banksAfter = await listBanks(mcpSessionId);
    console.log(`[E2E-MemoryBankRegistration] Memory banks after bootstrap: ${JSON.stringify(banksAfter)}`);

    // Verify the unique test bank from the dedicated config appears
    const testBank = banksAfter.find(bank => bank.name === UNIQUE_BANK);
    expect(testBank).toBeDefined();
    expect(testBank!.description).toBe('E2E memory bank registration verification');
    console.log('[E2E-MemoryBankRegistration] Unique test bank confirmed with correct description');

    // Verify default memory bank still present with hardcoded description
    const defaultBank = banksAfter.find(bank => bank.name === 'default');
    expect(defaultBank).toBeDefined();
    expect(defaultBank!.description).toBe(
      'Default personal memory — general conversation context, preferences, and facts',
    );
    console.log('[E2E-MemoryBankRegistration] Default memory bank still present with correct description');
  }, 30000);
});
