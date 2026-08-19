import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import { SessionMetadataService } from '@/infrastructure/services/session-metadata.service';
import { aSessionMetadataService } from '@/infrastructure/services/session-metadata.service.test-utils';
import * as fsSync from 'fs';
import * as os from 'os';
import * as path from 'path';

// Mock os so tests can override homedir() (os namespace import is not spyable).
jest.mock('os', () => {
  const actual = jest.requireActual<typeof import('os')>('os');
  return {
    ...actual,
    homedir: jest.fn(() => actual.homedir()),
  };
});

import {
  AgentSessionChunkingStrategy,
  buildCrossReferenceEdges,
  expandTilde,
  listSessionMdFiles,
} from './agent-session-chunking.strategy';
import { MastraChunkingService } from './mastra-chunking.service';
import { aMastraChunkingService } from './mastra-chunking.service.test-utils';

/** Creates a file with the given content (mkdirs parents). Returns absolute path. */
function writeFile(base: string, rel: string, content: string): string {
  const full = path.resolve(base, rel);
  fsSync.mkdirSync(path.dirname(full), { recursive: true });
  fsSync.writeFileSync(full, content, 'utf-8');
  return full;
}

/** Builds a standard fixture tree under a fresh tmp dir. */
interface FixtureTree {
  tmpBase: string;
  sessionRoot: string;
  otherSessionRoot: string;
  sessionMd: string;
  specMd: string;
  contractMd: string;
  archivedFindingsMd: string;
  otherSessionTargetMd: string;
}

function buildFixtureTree(): FixtureTree {
  const tmpBase = fsSync.mkdtempSync(path.join(os.tmpdir(), 'xref-test-'));
  const sessionRoot = path.join(tmpBase, 'a');
  const otherSessionRoot = path.join(tmpBase, 'b');

  const sessionMd = writeFile(sessionRoot, 'session.md', 'A session file');
  const specMd = writeFile(sessionRoot, 'specifications/spec.md', 'A spec file');
  const contractMd = writeFile(sessionRoot, 'materials/unified-chunk-contract.md', 'A contract');
  const archivedFindingsMd = writeFile(
    sessionRoot,
    'findings/archive/260819-0001-findings.md',
    'An archived findings file',
  );
  const otherSessionTargetMd = writeFile(otherSessionRoot, 'materials/b-contract.md', 'Session B contract');

  return {
    tmpBase,
    sessionRoot,
    otherSessionRoot,
    sessionMd,
    specMd,
    contractMd,
    archivedFindingsMd,
    otherSessionTargetMd,
  };
}

describe('expandTilde (agent-session cross-reference, D42 §2.2)', () => {
  it('expands a bare tilde to the home directory', () => {
    expect(expandTilde('~')).toBe(os.homedir());
  });

  it('expands a tilde-prefixed path to the home directory', () => {
    expect(expandTilde('~/foo/bar.md')).toBe(path.join(os.homedir(), 'foo', 'bar.md'));
  });

  it('leaves non-tilde tokens unchanged', () => {
    expect(expandTilde('specifications/spec.md')).toBe('specifications/spec.md');
    expect(expandTilde('/abs/path.md')).toBe('/abs/path.md');
  });
});

describe('listSessionMdFiles (agent-session cross-reference, D42 §2.2)', () => {
  let base: string;

  beforeEach(() => {
    base = fsSync.mkdtempSync(path.join(os.tmpdir(), 'xref-walk-'));
  });

  it('collects *.md files recursively', async () => {
    writeFile(base, 'session.md', 'x');
    writeFile(base, 'a/b/c/nested.md', 'x');
    writeFile(base, 'a/readme.txt', 'not md');
    writeFile(base, 'notes.md', 'x');

    const files = await listSessionMdFiles(base);

    const expected = [
      path.join(base, 'session.md'),
      path.join(base, 'a', 'b', 'c', 'nested.md'),
      path.join(base, 'notes.md'),
    ].sort();
    expect([...files].sort()).toEqual(expected);
  });

  it('respects the depth bound (maxDepth 4): depth-4 files in, depth-5 files out', async () => {
    writeFile(base, 'a/b/c/deep4.md', 'x'); // depth 4 — included
    writeFile(base, 'a/b/c/d/deep5.md', 'x'); // depth 5 — excluded

    const files = await listSessionMdFiles(base);

    expect(files).toContain(path.join(base, 'a', 'b', 'c', 'deep4.md'));
    expect(files).not.toContain(path.join(base, 'a', 'b', 'c', 'd', 'deep5.md'));
  });

  it('respects the file-count bound (maxFiles 200)', async () => {
    for (let i = 0; i < 205; i++) {
      writeFile(base, `f${i}.md`, 'x');
    }

    const files = await listSessionMdFiles(base);

    expect(files.length).toBe(200);
  });

  it('returns [] on fs error (nonexistent root)', async () => {
    const files = await listSessionMdFiles(path.join(base, 'does-not-exist'));
    expect(files).toEqual([]);
  });

  it('returns [] on fs error (readdir failure mid-walk)', async () => {
    // Make a subdirectory unreadable to force a readdir error during the walk.
    writeFile(base, 'a/ok.md', 'x');
    const blockedDir = path.join(base, 'blocked');
    fsSync.mkdirSync(blockedDir, { recursive: true });
    fsSync.writeFileSync(path.join(blockedDir, 'hidden.md'), 'x', 'utf-8');
    fsSync.chmodSync(blockedDir, 0o000);

    try {
      const files = await listSessionMdFiles(base);
      expect(files).toEqual([]);
    } finally {
      fsSync.chmodSync(blockedDir, 0o755);
    }
  });
});

describe('buildCrossReferenceEdges — Pass 1 path-pattern (D42 §2.2)', () => {
  let tree: FixtureTree;

  beforeEach(() => {
    tree = buildFixtureTree();
  });

  it('resolves a relative ref against the session root', async () => {
    const edges = await buildCrossReferenceEdges(
      'See specifications/spec.md for details',
      tree.sessionMd,
      tree.sessionRoot,
      [],
    );

    expect(edges).toHaveLength(1);
    expect(edges[0]).toEqual({
      target_path: tree.specMd,
      relation_type: 'cross_reference',
      strength: 0.7,
      description: 'content reference to specifications/spec.md',
    });
  });

  it('resolves an absolute ref as-is', async () => {
    const edges = await buildCrossReferenceEdges(
      `Refer to ${tree.contractMd} here`,
      tree.sessionMd,
      tree.sessionRoot,
      [],
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(tree.contractMd);
    expect(edges[0].relation_type).toBe('cross_reference');
    expect(edges[0].strength).toBe(0.7);
  });

  it('expands a tilde ref via os.homedir()', async () => {
    const tildeSpec = writeFile(tree.tmpBase, 'specs/spec.md', 'x');
    const homedirMock = os.homedir as unknown as jest.Mock;
    homedirMock.mockReturnValue(tree.tmpBase);

    try {
      const edges = await buildCrossReferenceEdges(
        'Tilde ref ~/specs/spec.md',
        tree.sessionMd,
        tree.sessionRoot,
        [],
      );

      expect(edges).toHaveLength(1);
      expect(edges[0].target_path).toBe(tildeSpec);
    } finally {
      homedirMock.mockRestore();
    }
  });

  it('emits a cross-session edge when the ref resolves into another session dir (existence-gated, NO containment guard)', async () => {
    // Absolute cross-session ref
    const edgesAbs = await buildCrossReferenceEdges(
      `Link ${tree.otherSessionTargetMd}`,
      tree.sessionMd,
      tree.sessionRoot,
      [],
    );
    expect(edgesAbs).toHaveLength(1);
    expect(edgesAbs[0].target_path).toBe(tree.otherSessionTargetMd);
    expect(edgesAbs[0].relation_type).toBe('cross_reference');

    // Relative cross-session ref (../b/... resolves outside sessionRoot)
    const edgesRel = await buildCrossReferenceEdges(
      'Link ../b/materials/b-contract.md',
      tree.sessionMd,
      tree.sessionRoot,
      [],
    );
    expect(edgesRel).toHaveLength(1);
    expect(edgesRel[0].target_path).toBe(tree.otherSessionTargetMd);
  });

  it('accepts targets from the sessionFiles list even without a stat check', async () => {
    const sessionFiles = [tree.contractMd];
    const edges = await buildCrossReferenceEdges(
      'Ref materials/unified-chunk-contract.md',
      tree.sessionMd,
      tree.sessionRoot,
      sessionFiles,
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(tree.contractMd);
  });

  it('emits no edge for a missing target', async () => {
    const edges = await buildCrossReferenceEdges(
      'Ref specifications/ghost.md and other/missing.md',
      tree.sessionMd,
      tree.sessionRoot,
      [],
    );

    expect(edges).toEqual([]);
  });

  it('emits no edge for a missing cross-session target', async () => {
    const edges = await buildCrossReferenceEdges(
      `Ref ${path.join(tree.otherSessionRoot, 'materials', 'nope.md')}`,
      tree.sessionMd,
      tree.sessionRoot,
      [],
    );

    expect(edges).toEqual([]);
  });

  it('emits no self edge when the content references the source file itself', async () => {
    const edges = await buildCrossReferenceEdges(
      `This is session.md itself`,
      tree.sessionMd,
      tree.sessionRoot,
      [tree.sessionMd],
    );

    expect(edges).toEqual([]);
  });

  it('dedupes duplicate refs to the same target', async () => {
    const content = 'A specifications/spec.md B specifications/spec.md C specifications/spec.md';
    const edges = await buildCrossReferenceEdges(content, tree.sessionMd, tree.sessionRoot, []);

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(tree.specMd);
  });

  it('extracts tokens with trailing punctuation (spec.md. → spec.md)', async () => {
    const edges = await buildCrossReferenceEdges(
      'See specifications/spec.md. The end',
      tree.sessionMd,
      tree.sessionRoot,
      [],
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(tree.specMd);
  });

  it('emits one edge per unique target across multiple refs', async () => {
    const edges = await buildCrossReferenceEdges(
      `Both specifications/spec.md and materials/unified-chunk-contract.md`,
      tree.sessionMd,
      tree.sessionRoot,
      [],
    );

    expect(edges).toHaveLength(2);
    const targets = edges.map(e => e.target_path).sort();
    expect(targets).toEqual([tree.contractMd, tree.specMd].sort());
    expect(edges.every(e => e.relation_type === 'cross_reference' && e.strength === 0.7)).toBe(true);
  });
});

describe('buildCrossReferenceEdges — Pass 2 basename (conservative, D42 §2.2)', () => {
  let tree: FixtureTree;

  beforeEach(() => {
    tree = buildFixtureTree();
  });

  it('matches a distinctive archive/ basename standalone', async () => {
    const edges = await buildCrossReferenceEdges(
      'Archived findings are in 260819-0001-findings.md.',
      tree.specMd,
      tree.sessionRoot,
      [tree.sessionMd, tree.specMd, tree.contractMd, tree.archivedFindingsMd],
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(tree.archivedFindingsMd);
    expect(edges[0].description).toBe('content reference to findings/archive/260819-0001-findings.md');
  });

  it('matches a unique-basename reference standalone', async () => {
    const edges = await buildCrossReferenceEdges(
      'The canonical contract lives in unified-chunk-contract.md as noted',
      tree.specMd,
      tree.sessionRoot,
      [tree.sessionMd, tree.specMd, tree.contractMd],
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(tree.contractMd);
  });

  it('matches a session.md basename reference from a non-self source file', async () => {
    const edges = await buildCrossReferenceEdges(
      'State is recorded in session.md',
      tree.specMd,
      tree.sessionRoot,
      [tree.sessionMd, tree.specMd],
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(tree.sessionMd);
  });

  it('does not match a basename preceded by path chars (avoids double-counting a path ref)', async () => {
    // Only a path-form ref; the basename is preceded by '/' so Pass 2 must not fire.
    const edges = await buildCrossReferenceEdges(
      'See specifications/spec.md only',
      tree.sessionMd,
      tree.sessionRoot,
      [tree.sessionMd, tree.specMd, tree.contractMd],
    );

    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(tree.specMd);
  });

  it('does not double-count when both a path ref and a standalone ref hit the same target', async () => {
    const edges = await buildCrossReferenceEdges(
      'Path form: specifications/spec.md. Short form: spec.md',
      tree.sessionMd,
      tree.sessionRoot,
      [tree.sessionMd, tree.specMd],
    );

    // One unique target ⇒ exactly one edge.
    expect(edges).toHaveLength(1);
    expect(edges[0].target_path).toBe(tree.specMd);
  });

  it('skips colliding basenames (>1 file share the basename) → no edge', async () => {
    const dupA = writeFile(tree.sessionRoot, 'a-notes/notes.md', 'x');
    const dupB = writeFile(tree.sessionRoot, 'b-notes/notes.md', 'x');
    void dupA;
    void dupB;

    const edges = await buildCrossReferenceEdges(
      'The notes.md we discussed',
      tree.specMd,
      tree.sessionRoot,
      [tree.sessionMd, tree.specMd, dupA, dupB],
    );

    expect(edges).toEqual([]);
  });
});

describe('buildCrossReferenceEdgesSafe (D42 §2.2 safe wrapper)', () => {
  it('returns [] when the algorithm throws', async () => {
    const sut = new AgentSessionChunkingStrategy(
      aSessionMetadataService() as unknown as SessionMetadataService,
      aMastraChunkingService() as unknown as MastraChunkingService,
      aLogger(),
    );

    const safe = (
      sut as unknown as {
        buildCrossReferenceEdgesSafe: (
          content: string,
          filePath: string,
          sessionRoot: string,
          sessionFiles: string[],
        ) => Promise<unknown>;
      }
    ).buildCrossReferenceEdgesSafe.bind(sut);

    // A non-string content makes the underlying algorithm throw; the wrapper must swallow it.
    const result = await safe(undefined as unknown as string, '/x/y.md', '/x', []);

    expect(result).toEqual([]);
  });
});
