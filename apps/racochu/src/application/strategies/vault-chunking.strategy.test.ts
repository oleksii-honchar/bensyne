import { FILE_ROLES } from '@/domain/content-chunk.entity';
import { aBodyChunk } from '@/domain/content-chunk.entity.test-utils';
import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import * as fsSync from 'fs';
import * as fsp from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { MastraChunkingService } from './mastra-chunking.service';
import { aMastraChunkingService } from './mastra-chunking.service.test-utils';
import { formatNoteMetadata } from './obsidian-chunking.strategy';
import {
  VaultChunkingStrategy,
  buildSeeAlsoEdges,
  buildWikilinkEdgesVault,
  cleanWikilinksForEmbedding,
  extractVaultNoteMetadata,
  isIndexFile,
  parseFrontmatterRecord,
  resolveWikilinkTarget,
} from './vault-chunking.strategy';

/**
 * Partial mock of fs/promises: delegates to the real implementation but makes
 * `readdir`/`stat` spyable (the real fs/promises namespace is non-configurable,
 * so jest.spyOn on the raw namespace fails).
 */
jest.mock('fs/promises', () => {
  const actual = jest.requireActual('fs/promises');
  return {
    ...actual,
    stat: jest.fn((...args: Parameters<typeof actual.stat>) => actual.stat(...args)),
    readdir: jest.fn((...args: Parameters<typeof actual.readdir>) => actual.readdir(...args)),
  };
});

// --- Temp vault fixture (real files on disk for fs-gated helpers) ---

interface VaultFixture {
  root: string;
  cleanup: () => void;
}

function createVaultFixture(): VaultFixture {
  const root = fsSync.mkdtempSync(path.join(os.tmpdir(), 'vault-strategy-test-'));
  fsSync.mkdirSync(path.join(root, 'concepts'), { recursive: true });
  fsSync.mkdirSync(path.join(root, 'decisions'), { recursive: true });
  // Root-level plain node
  fsSync.writeFileSync(path.join(root, 'RB_PLAIN.md'), '# Plain\n');
  // Typed concept nodes
  fsSync.writeFileSync(path.join(root, 'concepts', '0001-x.concept.md'), '# X\n');
  fsSync.writeFileSync(path.join(root, 'concepts', '0002-x.concept.md'), '# X2\n');
  // Decision nodes (one nested two levels deep for walk coverage)
  fsSync.writeFileSync(path.join(root, 'decisions', '0001-alpha.decision.md'), '# A\n');
  fsSync.writeFileSync(path.join(root, 'decisions', '0002-beta.decision.md'), '# B\n');
  fsSync.mkdirSync(path.join(root, 'decisions', 'archive'), { recursive: true });
  fsSync.writeFileSync(path.join(root, 'decisions', 'archive', '0003-old.decision.md'), '# Old\n');
  return {
    root,
    cleanup: () => fsSync.rmSync(root, { recursive: true, force: true }),
  };
}

// --- isIndexFile ---

describe('isIndexFile', () => {
  it('returns true for _index.md filename', () => {
    expect(isIndexFile('/vault/decisions/_index.md', null)).toBe(true);
  });

  it('returns true for _Vault-Home.md filename', () => {
    expect(isIndexFile('/vault/_Vault-Home.md', null)).toBe(true);
  });

  it('returns true for type: index frontmatter', () => {
    expect(isIndexFile('/vault/Home.md', 'type: index')).toBe(true);
  });

  it('returns false for a regular note', () => {
    expect(isIndexFile('/vault/concepts/0001-x.concept.md', 'type: concept')).toBe(false);
  });

  it('returns false when frontmatter is invalid YAML', () => {
    expect(isIndexFile('/vault/Note.md', 'key: [unclosed')).toBe(false);
  });
});

// --- parseFrontmatterRecord ---

describe('parseFrontmatterRecord', () => {
  it('parses valid YAML into a record', () => {
    const record = parseFrontmatterRecord('type: decision\nid: DEC-0001');
    expect(record).toEqual({ type: 'decision', id: 'DEC-0001' });
  });

  it('returns null for YAML that throws', () => {
    expect(parseFrontmatterRecord('key: [unclosed')).toBeNull();
  });

  it('returns null for scalar (non-object) YAML', () => {
    expect(parseFrontmatterRecord('just a string')).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(parseFrontmatterRecord('')).toBeNull();
  });
});

// --- extractVaultNoteMetadata ---

describe('extractVaultNoteMetadata', () => {
  it('maps vault frontmatter keys to NoteMetadata fields', () => {
    const frontmatter = [
      'type: decision',
      'status: approved',
      'id: DEC-0001',
      'system: racochu',
      'title: Alpha decision',
      'createdAt: 2026-08-01T10:00:00.000Z',
      'updatedAt: "2026-08-15"',
      'tags:',
      '  - vault',
      '  - decision',
      'see_also:',
      '  - concepts/0001-x.concept.md',
      'superseded_by: DEC-0002',
      'Deprecated: true',
      'Custom-Key: custom-value',
    ].join('\n');

    const meta = extractVaultNoteMetadata(frontmatter);

    expect(meta.type).toBe('decision');
    expect(meta.status).toBe('approved');
    expect(meta.tags).toEqual(['vault', 'decision']);
    expect(meta.created).toBe('2026-08-01T10:00:00.000Z');
    expect(meta.modified).toBe('2026-08-15');
    expect(meta.properties.id).toBe('DEC-0001');
    expect(meta.properties.system).toBe('racochu');
    expect(meta.properties.title).toBe('Alpha decision');
    expect(meta.properties.see_also).toBe(JSON.stringify(['concepts/0001-x.concept.md']));
    expect(meta.properties.superseded_by).toBe('DEC-0002');
    expect(meta.properties.deprecated).toBe('true');
    // other keys → lowercased
    expect(meta.properties['custom-key']).toBe('custom-value');
    // typed/consumed keys must not leak into properties
    expect(meta.properties).not.toHaveProperty('type');
    expect(meta.properties).not.toHaveProperty('status');
    expect(meta.properties).not.toHaveProperty('tags');
    expect(meta.properties).not.toHaveProperty('createdat');
    expect(meta.properties).not.toHaveProperty('updatedat');
  });

  it('stringifies object-valued keys (deprecated block)', () => {
    const frontmatter = ['deprecated:', '  by: DEC-0002', '  reason: outdated'].join('\n');
    const meta = extractVaultNoteMetadata(frontmatter);
    expect(meta.properties.deprecated).toBe(JSON.stringify({ by: 'DEC-0002', reason: 'outdated' }));
  });

  it('returns empty metadata for invalid YAML', () => {
    const meta = extractVaultNoteMetadata('key: [unclosed');
    expect(meta.type).toBe('');
    expect(meta.tags).toEqual([]);
    expect(meta.properties).toEqual({});
  });

  it('handles tags as a single string', () => {
    const meta = extractVaultNoteMetadata('tags: single-tag');
    expect(meta.tags).toEqual(['single-tag']);
  });
});

// --- buildSeeAlsoEdges ---

describe('buildSeeAlsoEdges', () => {
  let fixture: VaultFixture;
  let root: string;

  beforeEach(() => {
    fixture = createVaultFixture();
    root = fixture.root;
  });

  afterEach(() => {
    fixture.cleanup();
  });

  it('resolves block-array see_also values to recommendation edges', async () => {
    const record = parseFrontmatterRecord(
      ['see_also:', '  - concepts/0001-x.concept.md', '  - concepts/0002-x.concept.md'].join('\n'),
    );
    const edges = await buildSeeAlsoEdges(
      record,
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );

    expect(edges).toEqual([
      {
        target_path: path.join(root, 'concepts', '0001-x.concept.md'),
        relation_type: 'recommendation',
        strength: 1,
        description: expect.stringContaining('see_also'),
      },
      {
        target_path: path.join(root, 'concepts', '0002-x.concept.md'),
        relation_type: 'recommendation',
        strength: 1,
        description: expect.stringContaining('see_also'),
      },
    ]);
  });

  it('resolves inline-array see_also', async () => {
    const record = parseFrontmatterRecord('see_also: ["concepts/0001-x.concept.md"]');
    const edges = await buildSeeAlsoEdges(
      record,
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(path.join(root, 'concepts', '0001-x.concept.md'));
    expect(edges[0].relation_type).toBe('recommendation');
  });

  it('resolves single-string see_also', async () => {
    const record = parseFrontmatterRecord('see_also: concepts/0001-x.concept.md');
    const edges = await buildSeeAlsoEdges(
      record,
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(path.join(root, 'concepts', '0001-x.concept.md'));
  });

  it('retries with .md appended when value lacks extension and candidate is missing', async () => {
    const record = parseFrontmatterRecord('see_also: concepts/0002-x.concept');
    const edges = await buildSeeAlsoEdges(
      record,
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(path.join(root, 'concepts', '0002-x.concept.md'));
  });

  it('drops nonexistent ghost targets', async () => {
    const record = parseFrontmatterRecord('see_also: concepts/ghost.concept.md');
    const edges = await buildSeeAlsoEdges(
      record,
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );

    expect(edges).toEqual([]);
  });

  it('skips self-references', async () => {
    const selfPath = path.join(root, 'decisions', '0001-alpha.decision.md');
    const record = parseFrontmatterRecord('see_also: decisions/0001-alpha.decision.md');
    const edges = await buildSeeAlsoEdges(record, root, selfPath);

    expect(edges).toEqual([]);
  });

  it('ignores non-string entries', async () => {
    const record = parseFrontmatterRecord('see_also:\n  - 42\n  - concepts/0001-x.concept.md');
    const edges = await buildSeeAlsoEdges(
      record,
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(path.join(root, 'concepts', '0001-x.concept.md'));
  });

  it('returns [] when record has no see_also', async () => {
    const edges = await buildSeeAlsoEdges(
      parseFrontmatterRecord('type: decision'),
      root,
      path.join(root, 'x.md'),
    );
    expect(edges).toEqual([]);
  });

  it('returns [] for null record', async () => {
    const edges = await buildSeeAlsoEdges(null, root, path.join(root, 'x.md'));
    expect(edges).toEqual([]);
  });
});

// --- resolveWikilinkTarget ---

describe('resolveWikilinkTarget', () => {
  let fixture: VaultFixture;
  let root: string;

  beforeEach(() => {
    fixture = createVaultFixture();
    root = fixture.root;
  });

  afterEach(() => {
    fixture.cleanup();
  });

  it('resolves path-form target under vault root', async () => {
    const resolved = await resolveWikilinkTarget(
      'concepts/0001-x.concept',
      path.join(root, 'decisions', '0001-alpha.decision.md'),
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );
    expect(resolved).toBe(path.join(root, 'concepts', '0001-x.concept.md'));
  });

  it('resolves bare target to root-level node', async () => {
    const resolved = await resolveWikilinkTarget(
      'RB_PLAIN',
      path.join(root, 'decisions', '0001-alpha.decision.md'),
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );
    expect(resolved).toBe(path.join(root, 'RB_PLAIN.md'));
  });

  it('resolves bare target to same-folder node (2b before 2c)', async () => {
    const resolved = await resolveWikilinkTarget(
      '0002-beta.decision',
      path.join(root, 'decisions', '0001-alpha.decision.md'),
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );
    expect(resolved).toBe(path.join(root, 'decisions', '0002-beta.decision.md'));
  });

  it('resolves bare slug to typed node via vault-wide prefix match (2c)', async () => {
    const resolved = await resolveWikilinkTarget(
      '0001-x',
      path.join(root, 'RB_PLAIN.md'),
      root,
      path.join(root, 'RB_PLAIN.md'),
    );
    expect(resolved).toBe(path.join(root, 'concepts', '0001-x.concept.md'));
  });

  it('resolves bare slug to exact-stem node in subfolder (2c)', async () => {
    const resolved = await resolveWikilinkTarget(
      '0002-beta',
      path.join(root, 'RB_PLAIN.md'),
      root,
      path.join(root, 'RB_PLAIN.md'),
    );
    // decisions/0002-beta.decision.md matches via prefix '0002-beta.'
    expect(resolved).toBe(path.join(root, 'decisions', '0002-beta.decision.md'));
  });

  it('drops ambiguous bare targets (more than one candidate)', async () => {
    // '0002-x' matches concepts/0002-x.concept.md only in this fixture;
    // create a second candidate to force ambiguity
    fsSync.writeFileSync(path.join(root, 'decisions', '0002-x.decision.md'), '# dup\n');

    const resolved = await resolveWikilinkTarget(
      '0002-x',
      path.join(root, 'RB_PLAIN.md'),
      root,
      path.join(root, 'RB_PLAIN.md'),
    );
    expect(resolved).toBeUndefined();
  });

  it('drops nonexistent targets', async () => {
    const resolved = await resolveWikilinkTarget(
      'no-such-node',
      path.join(root, 'RB_PLAIN.md'),
      root,
      path.join(root, 'RB_PLAIN.md'),
    );
    expect(resolved).toBeUndefined();
  });

  it('skips self-references', async () => {
    const selfPath = path.join(root, 'concepts', '0001-x.concept.md');
    const resolved = await resolveWikilinkTarget('0001-x', selfPath, root, selfPath);
    expect(resolved).toBeUndefined();
  });

  it('is lazy: 2a/2b hits never trigger the vault walk (2c)', async () => {
    (fsp.readdir as jest.Mock).mockClear();

    // 2a hit: root-level node exists → walk must NOT be triggered
    const resolved = await resolveWikilinkTarget(
      'RB_PLAIN',
      path.join(root, 'decisions', '0001-alpha.decision.md'),
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );
    expect(resolved).toBe(path.join(root, 'RB_PLAIN.md'));
    expect(fsp.readdir).not.toHaveBeenCalled();

    (fsp.readdir as jest.Mock).mockClear();

    // 2b hit: same-folder node exists → walk must NOT be triggered either
    const sameFolderResolved = await resolveWikilinkTarget(
      '0002-beta.decision',
      path.join(root, 'decisions', '0001-alpha.decision.md'),
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );
    expect(sameFolderResolved).toBe(path.join(root, 'decisions', '0002-beta.decision.md'));
    expect(fsp.readdir).not.toHaveBeenCalled();
  });

  it('triggers the vault walk (2c) only when 2a/2b miss', async () => {
    (fsp.readdir as jest.Mock).mockClear();

    // Bare slug '0001-x' misses 2a/2b → walk must run and find the typed node
    const resolved = await resolveWikilinkTarget(
      '0001-x',
      path.join(root, 'RB_PLAIN.md'),
      root,
      path.join(root, 'RB_PLAIN.md'),
    );
    expect(resolved).toBe(path.join(root, 'concepts', '0001-x.concept.md'));
    expect(fsp.readdir).toHaveBeenCalled();
  });
});

// --- buildWikilinkEdgesVault ---

describe('buildWikilinkEdgesVault', () => {
  let fixture: VaultFixture;
  let root: string;

  beforeEach(() => {
    fixture = createVaultFixture();
    root = fixture.root;
  });

  afterEach(() => {
    fixture.cleanup();
  });

  it('emits backlink edges for resolvable wikilinks only', async () => {
    const edges = await buildWikilinkEdgesVault(
      ['concepts/0001-x.concept', 'no-such-node'],
      path.join(root, 'decisions', '0001-alpha.decision.md'),
      root,
      path.join(root, 'decisions', '0001-alpha.decision.md'),
    );

    expect(edges).toEqual([
      {
        target_path: path.join(root, 'concepts', '0001-x.concept.md'),
        relation_type: 'backlink',
        strength: 1,
        description: expect.stringContaining('wikilink'),
      },
    ]);
  });

  it('returns [] when no wikilinks', async () => {
    const edges = await buildWikilinkEdgesVault([], path.join(root, 'a.md'), root, path.join(root, 'a.md'));
    expect(edges).toEqual([]);
  });
});

// --- cleanWikilinksForEmbedding ---

describe('cleanWikilinksForEmbedding', () => {
  it('replaces [[t|a]] with alias', () => {
    expect(cleanWikilinksForEmbedding('See [[my-node|the node]] here.')).toBe('See the node here.');
  });

  it('replaces [[t]] with target', () => {
    expect(cleanWikilinksForEmbedding('See [[my-node]] here.')).toBe('See my-node here.');
  });

  it('replaces heading links [[t#h]] with target', () => {
    expect(cleanWikilinksForEmbedding('See [[my-node#Section]] here.')).toBe('See my-node here.');
  });

  it('replaces embeds ![[t]] with target', () => {
    expect(cleanWikilinksForEmbedding('Embed: ![[my-node]] end.')).toBe('Embed: my-node end.');
  });

  it('leaves text without wikilinks unchanged', () => {
    expect(cleanWikilinksForEmbedding('Plain text, no links.')).toBe('Plain text, no links.');
  });
});

// --- VaultChunkingStrategy.chunkFile ---

describe('VaultChunkingStrategy', () => {
  let sut: VaultChunkingStrategy;
  let mockMastra: ReturnType<typeof aMastraChunkingService>;
  let fixture: VaultFixture;
  let root: string;

  const vaultConfig = (vaultRoot: string) =>
    aWatchSourceConfig({
      id: 'test-source',
      path: vaultRoot,
      memoryBank: 'test-source',
      exclude: ['**/node_modules/**'],
      sourceType: 'vault',
    });

  beforeEach(() => {
    jest.clearAllMocks();
    fixture = createVaultFixture();
    root = fixture.root;
    mockMastra = aMastraChunkingService([aBodyChunk()]);
    sut = new VaultChunkingStrategy(mockMastra as unknown as MastraChunkingService, aLogger());
  });

  afterEach(() => {
    fixture.cleanup();
  });

  it('has chunkFile method with correct signature', () => {
    expect(typeof sut.chunkFile).toBe('function');
  });

  describe('index skip', () => {
    it('skips _index.md by filename', async () => {
      const result = await sut.chunkFile(
        '# Folder index\nLinks: [[0001-x]]\n',
        path.join(root, 'concepts', '_index.md'),
        'test-source',
        vaultConfig(root),
      );
      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual([]);
    });

    it('skips _Vault-Home.md by filename', async () => {
      const result = await sut.chunkFile(
        '# Home\n',
        path.join(root, '_Vault-Home.md'),
        'test-source',
        vaultConfig(root),
      );
      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual([]);
    });

    it('skips type: index frontmatter', async () => {
      const result = await sut.chunkFile(
        '---\ntype: index\n---\n# Index note\n',
        path.join(root, 'Home.md'),
        'test-source',
        vaultConfig(root),
      );
      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual([]);
    });
  });

  describe('full pipeline', () => {
    // Lazy accessor — root is set in beforeEach
    const NOTE_PATH = () => path.join(root, 'decisions', '0001-alpha.decision.md');

    const NOTE_CONTENT = [
      '---',
      'type: decision',
      'id: DEC-0001',
      'system: racochu',
      'tags:',
      '  - decision',
      'see_also:',
      '  - concepts/0001-x.concept.md',
      '---',
      'Decision body links [[0001-x|the concept]] and [[RB_PLAIN]].',
    ].join('\n');

    it('creates frontmatter chunk (0.9 importance, vault-node tag) + body chunks with edges and metadata', async () => {
      const result = await sut.chunkFile(NOTE_CONTENT, NOTE_PATH(), 'test-source', vaultConfig(root));

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBe(2);

      const fmChunk = chunks[0];
      expect(fmChunk.importance).toBe(0.9);
      expect(fmChunk.sectionHeader).toBe('Frontmatter');
      expect(fmChunk.text).toMatch(/^---\n[\s\S]*\n---$/);
      expect(fmChunk.tags).toContain('frontmatter');
      expect(fmChunk.tags).toContain('metadata');
      expect(fmChunk.tags).toContain('vault-node');
      expect(fmChunk.fileRole).toBe(FILE_ROLES.DOCS);
      expect(fmChunk.memoryBank).toBe('default');

      // Vault-aware metadata mapping via exported formatNoteMetadata convention
      expect(fmChunk.metadata?.['note.type']).toBe('decision');
      expect(fmChunk.metadata?.['note.properties.id']).toBe('DEC-0001');
      expect(fmChunk.metadata?.['note.properties.system']).toBe('racochu');

      // Body chunk metadata enriched too
      const bodyChunk = chunks[1];
      expect(bodyChunk.metadata?.['note.type']).toBe('decision');
      expect(bodyChunk.metadata?.['note.properties.id']).toBe('DEC-0001');
      expect(bodyChunk.tags).toContain('decision');
    });

    it('attaches see_also recommendation edge and wikilink backlink edges to ALL chunks', async () => {
      const result = await sut.chunkFile(NOTE_CONTENT, NOTE_PATH(), 'test-source', vaultConfig(root));
      const chunks = result.getValue();

      for (const chunk of chunks) {
        expect(chunk.edges).toBeDefined();
        const targetPaths = chunk.edges?.map(e => e.target_path) ?? [];
        // see_also → recommendation
        expect(targetPaths).toContain(path.join(root, 'concepts', '0001-x.concept.md'));
        const recEdge = chunk.edges?.find(
          e => e.target_path === path.join(root, 'concepts', '0001-x.concept.md'),
        );
        expect(recEdge?.relation_type).toBe('recommendation');
        expect(recEdge?.strength).toBe(1);
        // wikilinks → backlink (bare slug prefix + bare root)
        const backlinkTargets = (chunk.edges ?? [])
          .filter(e => e.relation_type === 'backlink')
          .map(e => e.target_path);
        expect(backlinkTargets).toContain(path.join(root, 'concepts', '0001-x.concept.md'));
        expect(backlinkTargets).toContain(path.join(root, 'RB_PLAIN.md'));
        // note.wikilinks + note.see_also metadata
        expect(JSON.parse(chunk.metadata!['note.wikilinks'])).toEqual(['0001-x', 'RB_PLAIN']);
        expect(JSON.parse(chunk.metadata!['note.see_also'])).toEqual(['concepts/0001-x.concept.md']);
      }
    });

    it('passes CLEANED body to Mastra (no [[wikilinks]] in embedded text)', async () => {
      await sut.chunkFile(NOTE_CONTENT, NOTE_PATH(), 'test-source', vaultConfig(root));
      const expectedCleanedBody = 'Decision body links the concept and RB_PLAIN.';
      expect(mockMastra.chunkFile).toHaveBeenCalledWith(expectedCleanedBody, NOTE_PATH(), 'test-source');
    });

    it('re-indexes final list densely 0..m-1 with totalChunks = m (D41)', async () => {
      mockMastra = aMastraChunkingService([aBodyChunk({ chunkIndex: 0 }), aBodyChunk({ chunkIndex: 1 })]);
      sut = new VaultChunkingStrategy(mockMastra as unknown as MastraChunkingService, aLogger());

      const result = await sut.chunkFile(NOTE_CONTENT, NOTE_PATH(), 'test-source', vaultConfig(root));
      const chunks = result.getValue();
      expect(chunks.length).toBe(3);
      expect(chunks.map(c => c.chunkIndex)).toEqual([0, 1, 2]);
      for (const chunk of chunks) {
        expect(chunk.totalChunks).toBe(3);
      }
    });

    it('omits note.wikilinks / note.see_also and edges when nothing present', async () => {
      const content = '---\ntype: note\n---\nPlain body, no links.\n';
      const result = await sut.chunkFile(
        content,
        path.join(root, 'plain.md'),
        'test-source',
        vaultConfig(root),
      );
      const chunks = result.getValue();
      for (const chunk of chunks) {
        expect(chunk.edges).toBeUndefined();
        expect(chunk.metadata?.['note.wikilinks']).toBeUndefined();
        expect(chunk.metadata?.['note.see_also']).toBeUndefined();
      }
    });

    it('attaches only resolved edges (unresolvable wikilink dropped)', async () => {
      const content = '---\ntype: note\n---\nLinks [[concepts/0002-x.concept]] and [[ghost-node]].\n';
      const result = await sut.chunkFile(
        content,
        path.join(root, 'decisions', '0002-beta.decision.md'),
        'test-source',
        vaultConfig(root),
      );
      const chunks = result.getValue();
      for (const chunk of chunks) {
        expect(chunk.edges).toHaveLength(1);
        expect(chunk.edges?.[0].target_path).toBe(path.join(root, 'concepts', '0002-x.concept.md'));
      }
    });
  });

  describe('degrade-on-error (never Result.ko from vault logic)', () => {
    const NOTE_PATH = () => path.join(root, 'decisions', '0001-alpha.decision.md');

    it('degrades to frontmatter-only chunks when Mastra returns ko', async () => {
      mockMastra = aMastraChunkingService();
      (mockMastra.chunkFile as jest.Mock).mockResolvedValueOnce({
        isOk: () => false,
        isKo: () => true,
        getValue: () => {
          throw new Error('ko');
        },
        getErrors: () => [],
        map: jest.fn(),
        chain: jest.fn(),
        getEvents: () => [],
        hasEvents: () => false,
      });
      sut = new VaultChunkingStrategy(mockMastra as unknown as MastraChunkingService, aLogger());

      const result = await sut.chunkFile(
        '---\ntype: decision\nid: DEC-0001\n---\nBody.\n',
        NOTE_PATH(),
        'test-source',
        vaultConfig(root),
      );
      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks).toHaveLength(1);
      expect(chunks[0].sectionHeader).toBe('Frontmatter');
    });

    it('still returns ok with chunks when see_also targets are ghosts (fs gate drops edges)', async () => {
      const content = ['---', 'type: decision', 'see_also:', '  - ghost/missing.md', '---', 'Body.\n'].join(
        '\n',
      );

      const result = await sut.chunkFile(content, NOTE_PATH(), 'test-source', vaultConfig(root));
      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBeGreaterThan(0);
      for (const chunk of chunks) {
        expect(chunk.edges).toBeUndefined();
      }
    });

    it('still returns ok with chunks when frontmatter YAML is invalid', async () => {
      const content = '---\nkey: [unclosed\n---\nBody with [[0001-x]] link.\n';

      const result = await sut.chunkFile(content, NOTE_PATH(), 'test-source', vaultConfig(root));
      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBeGreaterThan(0);
    });
  });

  describe('tag clamp (≤ 20, no throw)', () => {
    it('clamps merged tags to 20 when note + existing tags exceed the limit', async () => {
      const noteTags = Array.from({ length: 18 }, (_, i) => `ntag-${i}`);
      const existingTags = Array.from({ length: 10 }, (_, i) => `etag-${i}`);
      const bodyChunk = aBodyChunk({ tags: existingTags });
      mockMastra = aMastraChunkingService([bodyChunk]);
      sut = new VaultChunkingStrategy(mockMastra as unknown as MastraChunkingService, aLogger());

      const content = ['---', 'type: note', 'tags:', ...noteTags.map(t => `  - ${t}`), '---', 'Body.\n'].join(
        '\n',
      );

      const result = await sut.chunkFile(
        content,
        path.join(root, 'many-tags.md'),
        'test-source',
        vaultConfig(root),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      for (const chunk of chunks) {
        expect(chunk.tags.length).toBeLessThanOrEqual(20);
      }
      // Frontmatter chunk: base tags + note tags clamped to 20
      expect(chunks[0].tags).toHaveLength(20);
      expect(chunks[0].tags).toContain('frontmatter');
      // Body chunk: existing + note tags clamped to 20, existing tags preserved first
      expect(chunks[1].tags).toHaveLength(20);
      expect(chunks[1].tags.slice(0, 10)).toEqual(existingTags);
    });
  });

  describe('formatNoteMetadata export usage', () => {
    it('imports and uses formatNoteMetadata for note.* keys (shared convention)', async () => {
      // The vault strategy must produce the same note.* keys as the obsidian convention
      // Sanity: the exported formatter is what vault strategy relies on
      expect(typeof formatNoteMetadata).toBe('function');

      // Run vault chunkFile and assert the note.* shape matches formatNoteMetadata output
      mockMastra = aMastraChunkingService([]);
      sut = new VaultChunkingStrategy(mockMastra as unknown as MastraChunkingService, aLogger());
      const result = await sut.chunkFile(
        '---\ntype: decision\nid: DEC-0001\ntags:\n  - decision\ncreatedAt: 2026-01-01\n---\nBody.\n',
        path.join(root, 'decisions', '0001-alpha.decision.md'),
        'test-source',
        vaultConfig(root),
      );
      const fmMeta = result.getValue()[0].metadata ?? {};
      const expected = formatNoteMetadata({
        aliases: [],
        tags: ['decision'],
        created: '2026-01-01',
        modified: '',
        source: '',
        status: '',
        type: 'decision',
        base: '',
        properties: { id: 'DEC-0001' },
      });

      for (const [key, value] of Object.entries(expected)) {
        expect(fmMeta[key]).toBe(value);
      }
    });
  });
});
