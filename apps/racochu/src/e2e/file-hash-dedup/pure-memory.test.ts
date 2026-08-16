import { BensyneClient } from '@/infrastructure/services/bensyne-client.service';
import { INestApplication } from '@nestjs/common';
import { ContentChunk } from '../../domain/content-chunk.entity';
import { createTestApplication } from '../main.test-application';

describe('[E2E] File Hash Dedup — Pure Memory (No Hash) Continues Normally', () => {
  let app: INestApplication | null = null;
  let bensyneClient: BensyneClient | null = null;

  beforeAll(async () => {
    app = await createTestApplication();
    await app.init();

    bensyneClient = app.get(BensyneClient);
    console.log(`[E2E-PureMemory] Server bootstrapped, BensyneClient ready`);
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
  });

  it('should store a pure memory without fileHash and recall it normally', async () => {
    const uniqueId = Date.now();
    const marker = `PUREMEM-${uniqueId}`;

    // Create a ContentChunk with NO fileHash or hardwareId in metadata
    // This simulates a conversation memory or any non-file-based memory
    const chunk = ContentChunk.of({
      id: BigInt(uniqueId),
      text: `This is a pure memory without any file hash. Test marker: ${marker}. Pure memories should bypass dedup and be stored normally.`,
      chunkIndex: 0,
      totalChunks: 1,
      sectionHeader: 'Pure Memory Test',
      breadcrumb: 'root > pure-memory',
      fileRole: 'docs',
      oversized: false,
      importance: 0.5,
      tags: [],
      metadata: {}, // Empty metadata — no fileHash, no hardwareId
      memoryBank: 'e2e-test-ns',
    });

    expect(chunk.isOk()).toBe(true);
    const chunkValue = chunk.getValue();

    // Verify the chunk has no fileHash in metadata
    expect(chunkValue.metadata).toBeDefined();
    expect(chunkValue.metadata).not.toHaveProperty('fileHash');
    expect(chunkValue.metadata).not.toHaveProperty('hardwareId');
    console.log(
      `[E2E-PureMemory] Chunk created without fileHash: id=${chunkValue.id}, textLength=${chunkValue.text.length}`,
    );

    // Step 1: Remember the pure memory — should return "stored", not "deduplicated"
    const rememberResult = await bensyneClient!.remember(chunkValue);
    expect(rememberResult.isOk()).toBe(true);
    const rememberData = rememberResult.getValue();
    console.log(
      `[E2E-PureMemory] Remember result: status="${rememberData.status}", memory_id="${rememberData.memory_id}"`,
    );

    // Verify status is "stored" — not "deduplicated"
    expect(rememberData.status).toBe('stored');
    expect(rememberData.memory_id).toBeDefined();
    expect(rememberData.memory_id.length).toBeGreaterThan(0);

    // Step 2: Wait briefly for Mnemosyne to index the memory
    await new Promise(resolve => setTimeout(resolve, 5000));

    // Step 3: Recall the memory — should find it
    const recallResult = await bensyneClient!.recall(marker, 5, 1000, 'e2e-test-ns');
    expect(recallResult.isOk()).toBe(true);
    const recallResults = recallResult.getValue();
    console.log(`[E2E-PureMemory] Recall returned ${recallResults.length} results`);

    expect(recallResults.length).toBeGreaterThan(0);
    expect(recallResults.some(r => r.includes(marker))).toBe(true);
    console.log(`[E2E-PureMemory] Pure memory stored and recalled successfully`);
  }, 60000);
});
