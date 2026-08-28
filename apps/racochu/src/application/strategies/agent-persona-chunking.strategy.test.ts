import * as fsSync from 'fs';
import * as fsp from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { ContentChunk } from '../../domain/content-chunk.entity';
import { aSourceConfig } from '../../infrastructure/config/configuration.service.test-utils';
import { aLogger } from '../../infrastructure/logging/logger.test-utils';
import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';
import {
  AgentPersonaChunkingStrategy,
  buildFolderHierarchyEdges,
  buildPersonaDecisionEdges,
  expandHome,
  extractPersonaNodeMetadata,
} from './agent-persona-chunking.strategy';

const TREE_ROOT = '/home/ops/agent-personas/architect';

describe('expandHome (~ expansion for watchSource paths, RC1)', () => {
  const home = os.homedir();

  it('expands a bare ~ to the home directory', () => {
    expect(expandHome('~')).toBe(home);
  });

  it('expands a ~/relative path against the home directory', () => {
    expect(expandHome('~/Documents/agent-rules-n-skills/agent-personas/researcher')).toBe(
      path.join(home, 'Documents/agent-rules-n-skills/agent-personas/researcher'),
    );
  });

  it('expands a backslash-prefixed ~ path', () => {
    expect(expandHome('~\\x\\y')).toBe(path.join(home, 'x\\y'));
  });

  it('leaves absolute, relative, and tilde-less paths unchanged', () => {
    expect(expandHome('/opt/personas/architect')).toBe('/opt/personas/architect');
    expect(expandHome('relative/personas')).toBe('relative/personas');
  });
});

/** File index for the canonical example tree (spec §3.0). */
const EXAMPLE_INDEX = [
  path.join(TREE_ROOT, '00-entry.md'),
  path.join(TREE_ROOT, '10-understand/10-assess-intent.md'),
  path.join(TREE_ROOT, '10-understand/20-clarify.md'),
  path.join(TREE_ROOT, '20-plan/10-estimate.md'),
  path.join(TREE_ROOT, '20-plan/20-risk.md'),
  path.join(TREE_ROOT, '30-deliver/10-implement.md'),
];

describe('extractPersonaNodeMetadata (§4.1 frontmatter contract)', () => {
  it('parses all contract fields including temporality', () => {
    const frontmatter = [
      'id: 00-entry',
      'title: Entry',
      'entry: true',
      'conditions:',
      '  - always',
      'veto: []',
      'edges:',
      '  - target: 10-understand/10-assess-intent.md',
      '    when: intent is unclear',
      'created: 2026-08-26',
      'updated: 2026-08-26',
      'status: active',
      'valid_until: 2026-12-31',
      'supersedes: 00-entry-legacy',
    ].join('\n');

    const meta = extractPersonaNodeMetadata(frontmatter, '/any/00-entry.md');

    expect(meta.nodeId).toBe('00-entry');
    expect(meta.title).toBe('Entry');
    expect(meta.entry).toBe(true);
    expect(meta.conditions).toEqual(['always']);
    expect(meta.veto).toEqual([]);
    expect(meta.edges).toEqual([{ target: '10-understand/10-assess-intent.md', when: 'intent is unclear' }]);
    expect(meta.created).toBe('2026-08-26');
    expect(meta.updated).toBe('2026-08-26');
    expect(meta.status).toBe('active');
    expect(meta.validUntil).toBe('2026-12-31');
    expect(meta.supersedes).toBe('00-entry-legacy');
  });

  it('falls back to filename stem for node id and title when absent (ADR-9: filename == node id)', () => {
    const meta = extractPersonaNodeMetadata('entry: false', `${TREE_ROOT}/10-understand/10-assess-intent.md`);

    expect(meta.nodeId).toBe('10-assess-intent');
    expect(meta.title).toBe('10-assess-intent');
    expect(meta.entry).toBe(false);
    expect(meta.edges).toEqual([]);
    expect(meta.created).toBeUndefined();
  });

  it('returns a safe default shape for missing/unparseable frontmatter', () => {
    const meta = extractPersonaNodeMetadata(null, `${TREE_ROOT}/00-entry.md`);

    expect(meta.nodeId).toBe('00-entry');
    expect(meta.edges).toEqual([]);
    expect(meta.entry).toBe(false);
  });
});

describe('buildPersonaDecisionEdges (frontmatter edges[] → decision_next)', () => {
  it('emits one decision_next edge per resolvable target, with when as description', () => {
    const meta = extractPersonaNodeMetadata(
      [
        'id: 00-entry',
        'edges:',
        '  - target: 10-understand/10-assess-intent.md',
        '    when: intent is unclear',
        '  - target: 20-plan/10-estimate.md',
        '    when: intent is clear',
      ].join('\n'),
      path.join(TREE_ROOT, '00-entry.md'),
    );

    const edges = buildPersonaDecisionEdges(meta, TREE_ROOT, path.join(TREE_ROOT, '00-entry.md'), EXAMPLE_INDEX);

    expect(edges).toHaveLength(2);
    expect(edges).toEqual([
      {
        target_path: path.join(TREE_ROOT, '10-understand/10-assess-intent.md'),
        relation_type: 'decision_next',
        strength: 1.0,
        description: 'intent is unclear',
      },
      {
        target_path: path.join(TREE_ROOT, '20-plan/10-estimate.md'),
        relation_type: 'decision_next',
        strength: 1.0,
        description: 'intent is clear',
      },
    ]);
  });

  it('skips dangling targets (not in the file index) while keeping resolvable edges intact', () => {
    const meta = extractPersonaNodeMetadata(
      [
        'id: 00-entry',
        'edges:',
        '  - target: 99-gone/99-removed.md',
        '    when: never resolves',
        '  - target: 10-understand/10-assess-intent.md',
        '    when: still resolves',
      ].join('\n'),
      path.join(TREE_ROOT, '00-entry.md'),
    );

    const edges = buildPersonaDecisionEdges(meta, TREE_ROOT, path.join(TREE_ROOT, '00-entry.md'), EXAMPLE_INDEX);

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(path.join(TREE_ROOT, '10-understand/10-assess-intent.md'));
    expect(edges[0].description).toBe('still resolves');
  });

  it('skips self-referencing edges', () => {
    const meta = extractPersonaNodeMetadata(
      ['id: 00-entry', 'edges:', '  - target: 00-entry.md', '    when: self loop'].join('\n'),
      path.join(TREE_ROOT, '00-entry.md'),
    );

    const edges = buildPersonaDecisionEdges(meta, TREE_ROOT, path.join(TREE_ROOT, '00-entry.md'), EXAMPLE_INDEX);

    expect(edges).toHaveLength(0);
  });
});

describe('buildFolderHierarchyEdges (nesting → folder_hierarchy, hub(parent) → hub(child))', () => {
  it('emits hub→hub edges for each nested folder containing node files', () => {
    const edges = buildFolderHierarchyEdges(TREE_ROOT, EXAMPLE_INDEX);

    expect(edges).toEqual([
      {
        target_path: path.join(TREE_ROOT, '10-understand/10-assess-intent.md'),
        relation_type: 'folder_hierarchy',
        strength: 1.0,
        description: `folder branch 10-understand from 00-entry.md`,
      },
      {
        target_path: path.join(TREE_ROOT, '20-plan/10-estimate.md'),
        relation_type: 'folder_hierarchy',
        strength: 1.0,
        description: `folder branch 20-plan from 00-entry.md`,
      },
      {
        target_path: path.join(TREE_ROOT, '30-deliver/10-implement.md'),
        relation_type: 'folder_hierarchy',
        strength: 1.0,
        description: `folder branch 30-deliver from 00-entry.md`,
      },
    ]);
  });

  it('chains deeper nesting: parent-folder hub → grandchild-folder hub', () => {
    const root = '/home/ops/agent-personas/deep';
    const index = [
      path.join(root, '00-entry.md'),
      path.join(root, '10-understand/10-assess-intent.md'),
      path.join(root, '10-understand/20-details/10-probe.md'),
    ];

    const edges = buildFolderHierarchyEdges(root, index);

    // root hub → 10-understand hub
    expect(
      edges.find(e => e.target_path === path.join(root, '10-understand/10-assess-intent.md'))?.target_path,
    ).toBe(path.join(root, '10-understand/10-assess-intent.md'));
    // 10-understand hub → 20-details hub
    expect(
      edges.find(e => e.target_path === path.join(root, '10-understand/20-details/10-probe.md'))?.target_path,
    ).toBe(path.join(root, '10-understand/20-details/10-probe.md'));
    expect(edges).toHaveLength(2);
  });

  it('emits nothing for a flat tree (no nested folders)', () => {
    expect(buildFolderHierarchyEdges(TREE_ROOT, [path.join(TREE_ROOT, '00-entry.md')])).toEqual([]);
  });
});

describe('AgentPersonaChunkingStrategy.chunkFile — one memory per node', () => {
  let tmpRoot: string;

  beforeEach(async () => {
    tmpRoot = await fsp.mkdtemp(path.join(os.tmpdir(), 'persona-chunker-'));
    fsSync.mkdirSync(path.join(tmpRoot, '10-understand'), { recursive: true });
    fsSync.writeFileSync(
      path.join(tmpRoot, '00-entry.md'),
      '---\nid: 00-entry\ntitle: Entry\nentry: true\nedges:\n  - target: 10-understand/10-assess-intent.md\n    when: always first\ncreated: 2026-08-26\nupdated: 2026-08-26\nstatus: active\nvalid_until: 2026-12-31\nsupersedes: 00-entry-legacy\n---\nGreet and assess.',
    );
    fsSync.writeFileSync(
      path.join(tmpRoot, '10-understand/10-assess-intent.md'),
      '---\nid: 10-assess-intent\ntitle: Assess intent\n---\nRead the ask.',
    );
  });

  afterEach(async () => {
    await fsp.rm(tmpRoot, { recursive: true, force: true });
  });

  const buildStrategy = () => new AgentPersonaChunkingStrategy(aLogger());

  it('returns exactly one chunk: content = title + body, tags, node metadata', async () => {
    const strategy = buildStrategy();
    const sourceConfig = aSourceConfig({ id: 'persona-architect', path: tmpRoot, sourceType: 'agent-persona' });

    const result = await strategy.chunkFile(
      fsSync.readFileSync(path.join(tmpRoot, '00-entry.md'), 'utf-8'),
      path.join(tmpRoot, '00-entry.md'),
      'persona-architect',
      sourceConfig,
    );

    expect(result.isOk()).toBe(true);
    const chunks = result.getValue();
    expect(chunks).toHaveLength(1);
    const chunk = chunks[0];
    expect(chunk.text).toContain('Entry');
    expect(chunk.text).toContain('Greet and assess.');
    expect(chunk.tags).toEqual(['persona-node', '00-entry']);
    expect(chunk.fileRole).toBe('docs');
    expect(chunk.sectionHeader).toBe('Entry');
  });

  it('stamps the full metadata set (identity, traversal, temporality)', async () => {
    const strategy = buildStrategy();
    const sourceConfig = aSourceConfig({ id: 'persona-architect', path: tmpRoot, sourceType: 'agent-persona' });
    const content = fsSync.readFileSync(path.join(tmpRoot, '00-entry.md'), 'utf-8');

    const result = await strategy.chunkFile(
      content,
      path.join(tmpRoot, '00-entry.md'),
      'persona-architect',
      sourceConfig,
    );

    const metadata = result.getValue()[0].metadata ?? {};
    expect(metadata['persona.node_id']).toBe('00-entry');
    expect(metadata['persona.title']).toBe('Entry');
    expect(metadata['persona.entry']).toBe('true');
    expect(metadata['persona.conditions']).toBe('[]');
    expect(metadata['persona.veto']).toBe('[]');
    expect(metadata['persona.created']).toBe('2026-08-26');
    expect(metadata['persona.updated']).toBe('2026-08-26');
    expect(metadata['persona.status']).toBe('active');
    expect(metadata['persona.valid_until']).toBe('2026-12-31');
    expect(metadata['persona.supersedes']).toBe('00-entry-legacy');
  });

  it('attaches decision_next + folder_hierarchy edges to the hub node chunk', async () => {
    const strategy = buildStrategy();
    const sourceConfig = aSourceConfig({ id: 'persona-architect', path: tmpRoot, sourceType: 'agent-persona' });
    const content = fsSync.readFileSync(path.join(tmpRoot, '00-entry.md'), 'utf-8');

    const result = await strategy.chunkFile(
      content,
      path.join(tmpRoot, '00-entry.md'),
      'persona-architect',
      sourceConfig,
    );

    const edges = result.getValue()[0].edges ?? [];
    const decisionNext = edges.filter(e => e.relation_type === 'decision_next');
    const folderHierarchy = edges.filter(e => e.relation_type === 'folder_hierarchy');

    expect(decisionNext).toEqual([
      {
        target_path: path.join(tmpRoot, '10-understand/10-assess-intent.md'),
        relation_type: 'decision_next',
        strength: 1.0,
        description: 'always first',
      },
    ]);
    // 00-entry.md is the root hub; 10-understand is its only branch
    expect(folderHierarchy).toEqual([
      {
        target_path: path.join(tmpRoot, '10-understand/10-assess-intent.md'),
        relation_type: 'folder_hierarchy',
        strength: 1.0,
        description: `folder branch 10-understand from 00-entry.md`,
      },
    ]);
  });

  it('a child node chunk carries no outgoing folder_hierarchy edges (it is not a hub)', async () => {
    const strategy = buildStrategy();
    const sourceConfig = aSourceConfig({ id: 'persona-architect', path: tmpRoot, sourceType: 'agent-persona' });
    const childPath = path.join(tmpRoot, '10-understand/10-assess-intent.md');
    const content = fsSync.readFileSync(childPath, 'utf-8');

    const result = await strategy.chunkFile(content, childPath, 'persona-architect', sourceConfig);

    const edges = result.getValue()[0].edges ?? [];
    expect(edges.filter(e => e.relation_type === 'folder_hierarchy')).toEqual([]);
  });

  it('propagates a Ko result from ContentChunk.of as a Ko chunkFile result (typed Result<ContentChunk[]>, no throw)', async () => {
    const strategy = buildStrategy();
    const sourceConfig = aSourceConfig({ id: 'persona-architect', path: tmpRoot, sourceType: 'agent-persona' });
    const content = fsSync.readFileSync(path.join(tmpRoot, '00-entry.md'), 'utf-8');
    const koError = new ErrorWithDetails('Invalid chunk data: forced failure', 'InvalidChunk');

    const spy = jest.spyOn(ContentChunk, 'of').mockReturnValue(Result.ko([koError]));
    try {
      const result: Result<ContentChunk[]> = await strategy.chunkFile(
        content,
        path.join(tmpRoot, '00-entry.md'),
        'persona-architect',
        sourceConfig,
      );

      expect(result.isKo()).toBe(true);
      expect(result.getErrors()).toEqual([koError]);
      expect(() => result.getValue()).toThrow(/Invalid chunk data: forced failure/);
    } finally {
      spy.mockRestore();
    }
  });
});

describe('AgentPersonaChunkingStrategy.chunkFile — tilde-prefixed tree roots (RC1)', () => {
  let treeRoot: string;

  beforeEach(async () => {
    // Tree lives under the real home — the same one expandHome resolves to —
    // so a `~`-prefixed watchSource path reaches it without mocking os.homedir
    // (not configurable in this jest/Node setup).
    treeRoot = await fsp.mkdtemp(path.join(os.homedir(), '.jest-persona-tilde-'));
    fsSync.mkdirSync(path.join(treeRoot, '10-investigate'), { recursive: true });
    fsSync.writeFileSync(
      path.join(treeRoot, '00-entry.md'),
      '---\nid: 00-entry\ntitle: Entry\nentry: true\nedges:\n  - target: 10-investigate/10-dig-in.md\n    when: always first\n---\nFrame the problem.',
    );
    fsSync.writeFileSync(
      path.join(treeRoot, '10-investigate/10-dig-in.md'),
      '---\nid: 10-dig-in\ntitle: Dig in\n---\nInvestigate.',
    );
  });

  afterEach(async () => {
    await fsp.rm(treeRoot, { recursive: true, force: true });
  });

  it('expands a ~ tree root so decision_next edges materialize', async () => {
    const strategy = new AgentPersonaChunkingStrategy(aLogger());
    const relative = path.relative(os.homedir(), treeRoot);
    const sourceConfig = aSourceConfig({
      id: 'persona-researcher',
      path: `~/${relative}`,
      sourceType: 'agent-persona',
    });
    const entryPath = path.join(treeRoot, '00-entry.md');
    const content = fsSync.readFileSync(entryPath, 'utf-8');

    const result = await strategy.chunkFile(content, entryPath, 'persona-researcher', sourceConfig);

    expect(result.isOk()).toBe(true);
    const edges = result.getValue()[0].edges ?? [];
    expect(edges).toEqual([
      {
        target_path: path.join(treeRoot, '10-investigate/10-dig-in.md'),
        relation_type: 'decision_next',
        strength: 1.0,
        description: 'always first',
      },
      {
        target_path: path.join(treeRoot, '10-investigate/10-dig-in.md'),
        relation_type: 'folder_hierarchy',
        strength: 1.0,
        description: 'folder branch 10-investigate from 00-entry.md',
      },
    ]);
  });
});
