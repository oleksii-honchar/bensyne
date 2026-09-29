import 'reflect-metadata';
import * as fs from 'fs';
import { AgentPersonaChunkingStrategy } from './src/application/strategies/agent-persona-chunking.strategy';
import { RememberRequestSerializer } from './src/infrastructure/mnemosyne/remember-request.serializer';
import { ContentChunk } from './src/domain/content-chunk.entity';
import { aWatchSourceConfig } from './src/domain/watch-source.entity.test-utils';
import { BasePinoLogger } from './src/infrastructure/logging/base-pino-logger';

const noop = (..._a: unknown[]) => undefined;
const logger = {
  setContext: noop,
  log: noop,
  info: noop,
  error: noop,
  warn: noop,
  debug: noop,
  child: (): BasePinoLogger => logger as unknown as BasePinoLogger,
} as unknown as BasePinoLogger;

async function main() {
  const filePath =
    '/Users/tuiteraz/www/beaver/agent-rules-n-skills/agent-personas/threads-operator/00-entry.md';
  const content = fs.readFileSync(filePath, 'utf8');
  console.log('content bytes:', Buffer.byteLength(content, 'utf8'));

  const strategy = new AgentPersonaChunkingStrategy(logger);
  const sourceConfig = aWatchSourceConfig({
    id: 'test-source',
    path: '/Users/tuiteraz/www/beaver/agent-rules-n-skills/agent-personas/threads-operator',
    memoryBank: 'default',
    exclude: [],
    sourceType: 'agent-persona',
  });

  const result = await strategy.chunkFile(content, filePath, 'test-source', sourceConfig);
  if (!result.isOk()) {
    console.log('KO:', result.getFormattedErrors());
    return;
  }
  const chunks = result.getValue();
  console.log('persona chunks:', chunks.length);

  const serializer = new RememberRequestSerializer();
  for (let i = 0; i < chunks.length; i++) {
    const serialized = serializer.buildAndSerialize(chunks[i]);
    const bytes = Buffer.byteLength(serialized, 'utf8');
    const edges = chunks[i].edges?.length ?? 0;
    const metaKeys = Object.keys(chunks[i].metadata ?? {}).length;
    console.log(
      `chunk[${i}] textBytes=${Buffer.byteLength(chunks[i].text, 'utf8')} edges=${edges} metaKeys=${metaKeys} serializedBytes=${bytes}`,
    );
  }

  // Simulate the chunk-content clamp (binary search + recursive split) to see how
  // many chunks the 4607-byte chunk explodes into at the 4000-byte limit.
  const MAX = 4000;
  const text = chunks[0].text;
  const clamped: string[] = [];
  const split = (t: string): void => {
    let low = 0;
    let high = t.length;
    while (low < high) {
      const mid = Math.floor((low + high + 1) / 2);
      const probe = chunks[0].toJson();
      probe.text = t.substring(0, mid);
      const probeBytes = Buffer.byteLength(serializer.buildAndSerialize(ContentChunk.of(probe).getValue()), 'utf8');
      if (probeBytes <= MAX) low = mid;
      else high = mid - 1;
    }
    if (low === 0) {
      clamped.push(t);
      return;
    }
    clamped.push(t.substring(0, low));
    const remainder = t.substring(low).trimStart();
    if (remainder.length > 0) split(remainder);
  };
  split(text);
  console.log('clamp-sim (persona chunk, no enrichment):', clamped.length);

  // Now add realistic enrichment metadata (title/keywords/summary) that the
  // EnhancementPipelineService injects BEFORE the clamp, then re-run the clamp.
  // Hypothesis: each split re-carries the full envelope → text budget shrinks →
  // hundreds of near-empty chunks.
  function runWithEnvelope(extraBytes: number, label: string): void {
    const base = chunks[0].toJson();
    base.metadata = {
      ...base.metadata,
      mastraDocTitle: 'T'.repeat(40),
      mastraDocKeywords: 'k,'.repeat(50),
      mastraDocSummary: 'S'.repeat(Math.max(10, extraBytes - 100)),
    };
    const enveloped = ContentChunk.of(base).getValue();
    const eBytes = Buffer.byteLength(serializer.buildAndSerialize(enveloped), 'utf8');
    const t = enveloped.text;
    let count = 0;
    const split2 = (tt: string): void => {
      let lo = 0;
      let hi = tt.length;
      while (lo < hi) {
        const mid = Math.floor((lo + hi + 1) / 2);
        const probe = enveloped.toJson();
        probe.text = tt.substring(0, mid);
        if (
          Buffer.byteLength(serializer.buildAndSerialize(ContentChunk.of(probe).getValue()), 'utf8') <= MAX
        ) {
          lo = mid;
        } else {
          hi = mid - 1;
        }
      }
      if (lo === 0) {
        count++;
        return;
      }
      count++;
      const rem = tt.substring(lo).trimStart();
      if (rem.length > 0) split2(rem);
    };
    split2(t);
    console.log(`clamp-sim (envelope +${extraBytes}B, total=${eBytes}B):`, count);
  }
  runWithEnvelope(100, '');
  runWithEnvelope(300, '');
  runWithEnvelope(500, '');
}

main().catch(e => console.error(e));