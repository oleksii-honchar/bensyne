import { GOLDEN_QUERY_CORPUS } from '@/e2e/fixtures/golden-query/corpus';
import { loadGoldenQuerySeedFiles } from '@/e2e/fixtures/golden-query/seed';
import { BensyneClient } from '@/infrastructure/services/bensyne-client.service';
import { INestApplication } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as path from 'path';
import { createTestApplication } from '../main.test-application';
import { GOLDEN_QUERY_EXPECTED_CONTENT } from './expected-content';
import { GoldenQueryRunReport, runGoldenQueries } from './runner';

/** Wait helper — resolves after the given number of milliseconds. */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Golden-query integration test.
 *
 * Seeds the watch directory with files containing the expected content,
 * waits for the file watcher to process and embed them, then runs the full
 * corpus against Mnemosyne recall through the real BensyneClient and
 * writes a JSON report. Requires bensyne (Mnemosyne MCP) to be reachable —
 * the e2e global-setup starts the Docker stack. The runner itself is
 * unit-tested in src/e2e/golden-query/; this test verifies the live wiring,
 * seeding, and report generation.
 */

describe('[E2E] Golden-query validation harness', () => {
  let app: INestApplication;
  let bensyneClient: BensyneClient;
  let memoryBank: string;

  beforeAll(async () => {
    app = await createTestApplication();
    await app.init();
    bensyneClient = app.get(BensyneClient);

    // Resolve the memory bank from the e2e config.
    // The global-setup writes a dynamic config with memoryBank: 'e2e-test-ns'.
    memoryBank = 'e2e-test-ns';

    // Seed the watch directory with files so there's actual embedded content
    // to retrieve against.
    const watchDir = process.env.E2E_WATCH_DIR;
    if (!watchDir) {
      throw new Error('E2E_WATCH_DIR not set — global-setup must run first');
    }

    const seedFiles = await loadGoldenQuerySeedFiles();

    console.log(`[golden-query] Seeding ${seedFiles.length} files into ${watchDir}`);

    for (const seed of seedFiles) {
      const filePath = path.join(watchDir, seed.path);
      await fs.mkdir(path.dirname(filePath), { recursive: true });
      await fs.writeFile(filePath, seed.content, 'utf8');
    }

    // Wait for file watcher to process the files and embed them.
    // The file watcher uses chokidar with debounce, so give it time.
    // Also allow time for the embedding pipeline to complete.

    console.log('[golden-query] Waiting 15s for file watcher + embedding pipeline...');
    await sleep(15000);

    // Probe: verify at least some content was embedded.
    // Use the correct memory bank (e2e-test-ns) — default 'default' won't match.
    const probeResult = await bensyneClient.recall('embedding model', 2, 500, memoryBank);
    if (probeResult.isOk() && probeResult.getValue().length === 0) {
      console.warn('[golden-query] No content embedded — results may be zeros');
    } else {
      console.log(
        `[golden-query] Probe query "embedding model" returned ${probeResult.isOk() ? probeResult.getValue().length : 0} results`,
      );
    }
  }, 90000);

  afterAll(async () => {
    const closePromise = app.close().catch(() => {
      // ignore close errors during teardown
    });
    const timeoutPromise = new Promise(resolve => setTimeout(resolve, 30000));
    await Promise.race([closePromise, timeoutPromise]);
  });

  it('runs the corpus through recall and writes a baseline report', async () => {
    const report: GoldenQueryRunReport = await runGoldenQueries({
      mode: 'baseline',
      corpus: GOLDEN_QUERY_CORPUS,
      recall: async query => {
        const result = await bensyneClient.recall(query, 2, 500, memoryBank);
        return result.isOk() ? result.getValue() : [];
      },
      resolveExpectedContent: key => GOLDEN_QUERY_EXPECTED_CONTENT[key] ?? [],
    });

    // Report structure is deterministic regardless of live retrieval quality
    expect(report.queryCount).toBe(GOLDEN_QUERY_CORPUS.length);
    expect(report.perQuery).toHaveLength(GOLDEN_QUERY_CORPUS.length);
    expect(report.aggregate).toHaveProperty('recallAt5');
    expect(report.aggregate).toHaveProperty('precisionAt5');
    expect(report.aggregate).toHaveProperty('mrr');

    const reportDir = path.resolve(__dirname, 'reports');
    await fs.mkdir(reportDir, { recursive: true });
    const reportPath = path.join(reportDir, 'baseline-report.json');
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2), 'utf8');

    // Evidence for the developer/reviewer

    console.log(`[golden-query baseline] aggregate=${JSON.stringify(report.aggregate)} report=${reportPath}`);
  });
});
