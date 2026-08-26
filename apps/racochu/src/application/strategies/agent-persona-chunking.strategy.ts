import { Injectable } from '@nestjs/common';
import * as fsp from 'fs/promises';
import * as yaml from 'js-yaml';
import * as path from 'path';
import { ContentChunk, FILE_ROLES, FileEdge } from '../../domain/content-chunk.entity';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { generateId } from '../../utils/big-endian-id';
import { Result } from '../../utils/result';
import { splitFrontmatter } from '../../utils/strategy-utils';
import { BaseChunkingStrategy, ChunkFileOptions } from './base-chunking-strategy';

/** Bounded tree-walk limits (vault parity). */
const MAX_WALK_DEPTH = 5;
const MAX_WALK_FILES = 500;

/**
 * Parsed §4.1 persona node frontmatter contract (ADR-9/ADR-10).
 * `nodeId`/`title` fall back to the filename stem (filename == node id).
 * Temporality fields are undefined when absent from the frontmatter.
 */
export interface PersonaNodeMetadata {
  nodeId: string;
  title: string;
  entry: boolean;
  conditions: string[];
  veto: string[];
  edges: { target: string; when?: string }[];
  created?: string;
  updated?: string;
  status?: string;
  validUntil?: string;
  supersedes?: string;
}

function stemOf(filePath: string): string {
  const base = path.basename(filePath);
  const ext = path.extname(base);
  return ext !== '' ? base.slice(0, -ext.length) : base;
}

function stringField(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim() !== '') {
    return value;
  }
  return undefined;
}

function toDateString(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim() !== '') {
    return value;
  }
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }
  return undefined;
}

function stringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string');
  }
  return [];
}

function parseEdges(value: unknown): { target: string; when?: string }[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const edges: { target: string; when?: string }[] = [];
  for (const item of value) {
    if (item === null || typeof item !== 'object' || Array.isArray(item)) {
      continue;
    }
    const record = item as Record<string, unknown>;
    const target = stringField(record.target);
    if (target === undefined) {
      continue;
    }
    const when = stringField(record.when);
    edges.push(when !== undefined ? { target, when } : { target });
  }
  return edges;
}

/**
 * Parses persona node frontmatter into the §4.1 contract.
 * Defensive: null/invalid frontmatter yields the stem-derived fallback shape.
 */
export function extractPersonaNodeMetadata(
  frontmatter: string | null,
  filePath: string,
): PersonaNodeMetadata {
  const stem = stemOf(filePath);
  let record: Record<string, unknown> | null = null;

  if (frontmatter !== null) {
    try {
      const parsed: unknown = yaml.load(frontmatter);
      if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
        record = parsed as Record<string, unknown>;
      }
    } catch {
      record = null;
    }
  }

  return {
    nodeId: stringField(record?.id) ?? stem,
    title: stringField(record?.title) ?? stem,
    entry: record?.entry === true || record?.entry === 'true',
    conditions: stringArray(record?.conditions),
    veto: stringArray(record?.veto),
    edges: parseEdges(record?.edges),
    created: toDateString(record?.created),
    updated: toDateString(record?.updated),
    status: stringField(record?.status),
    validUntil: toDateString(record?.valid_until),
    supersedes: stringField(record?.supersedes),
  };
}

/**
 * Builds `decision_next` edges from frontmatter `edges[]` (ADR-9).
 *
 * Targets are paths RELATIVE TO THE TREE ROOT (the watchSource path). Each
 * target is resolved against treeRoot and gated on the provided file index —
 * dangling targets are skipped (never crash ingestion); self-references skip.
 * Pure: file walking happens in the strategy, never here.
 */
export function buildPersonaDecisionEdges(
  meta: PersonaNodeMetadata,
  treeRoot: string,
  selfPath: string,
  fileIndex: string[],
): FileEdge[] {
  if (meta.edges.length === 0) {
    return [];
  }
  const index = new Set(fileIndex.map(f => path.resolve(f)));
  const resolvedSelf = path.resolve(selfPath);
  const edges: FileEdge[] = [];

  for (const edge of meta.edges) {
    const resolved = path.resolve(treeRoot, edge.target);
    if (resolved === resolvedSelf) {
      continue;
    }
    if (!index.has(resolved)) {
      continue; // dangling target → skipped (logged by the strategy)
    }
    edges.push({
      target_path: resolved,
      relation_type: 'decision_next',
      strength: 1.0,
      description: edge.when ?? '',
    });
  }

  return edges;
}

/** Internal folder-node: a folder with node files, its hub, and its children. */
interface FolderNode {
  folder: string;
  /** Lexicographically-first node file in the folder — the folder's hub. */
  hub: string;
  children: FolderNode[];
}

/**
 * Builds the folder tree from a file index: folder = branch, hub = first
 * `.md` in the folder (ADR-9: nested folders are the tree's visual structure).
 */
function buildFolderTree(treeRoot: string, fileIndex: string[]): FolderNode | null {
  const byFolder = new Map<string, string[]>();
  for (const f of fileIndex) {
    const resolved = path.resolve(f);
    const dir = path.dirname(resolved);
    const files = byFolder.get(dir) ?? [];
    files.push(resolved);
    byFolder.set(dir, files);
  }

  const childFolders = (folder: string): string[] => {
    const children: string[] = [];
    for (const dir of byFolder.keys()) {
      if (dir === folder) {
        continue;
      }
      const rel = path.relative(folder, dir);
      if (rel !== '' && !rel.startsWith('..') && !rel.includes(path.sep)) {
        children.push(dir);
      }
    }
    return children.sort();
  };

  const buildNode = (folder: string): FolderNode | null => {
    const files = (byFolder.get(folder) ?? []).slice().sort();
    if (files.length === 0) {
      return null;
    }
    const children = childFolders(folder)
      .map(child => buildNode(child))
      .filter((node): node is FolderNode => node !== null);
    return { folder, hub: files[0], children };
  };

  return buildNode(path.resolve(treeRoot));
}

function hierarchyEdge(sourceHub: string, child: FolderNode): FileEdge {
  return {
    target_path: child.hub,
    relation_type: 'folder_hierarchy',
    strength: 1.0,
    description: `folder branch ${path.basename(child.folder)} from ${path.basename(sourceHub)}`,
  };
}

/**
 * Builds structural `folder_hierarchy` edges from nesting (ADR-9): one edge per
 * folder branch, hub(parent folder) → hub(child folder), the human's folder
 * structure becoming graph structure for free. Deterministic: children sorted.
 */
export function buildFolderHierarchyEdges(treeRoot: string, fileIndex: string[]): FileEdge[] {
  const root = buildFolderTree(treeRoot, fileIndex);
  const edges: FileEdge[] = [];

  const walk = (node: FolderNode): void => {
    for (const child of node.children) {
      edges.push(hierarchyEdge(node.hub, child));
      walk(child);
    }
  };
  if (root !== null) {
    walk(root);
  }
  return edges;
}

/**
 * Flat chunk metadata for a persona node — namespaced `persona.` prefixed keys
 * (same convention as the session./note. prefixes). Temporality keys only when
 * present in the frontmatter.
 */
export function formatPersonaNodeMetadata(meta: PersonaNodeMetadata): Record<string, string> {
  const result: Record<string, string> = {
    'persona.node_id': meta.nodeId,
    'persona.title': meta.title,
    'persona.entry': String(meta.entry),
    'persona.conditions': JSON.stringify(meta.conditions),
    'persona.veto': JSON.stringify(meta.veto),
  };
  if (meta.created !== undefined) {
    result['persona.created'] = meta.created;
  }
  if (meta.updated !== undefined) {
    result['persona.updated'] = meta.updated;
  }
  if (meta.status !== undefined) {
    result['persona.status'] = meta.status;
  }
  if (meta.validUntil !== undefined) {
    result['persona.valid_until'] = meta.validUntil;
  }
  if (meta.supersedes !== undefined) {
    result['persona.supersedes'] = meta.supersedes;
  }
  return result;
}

/**
 * Agent-persona decision-tree chunker (ADR-2 package pattern, spec §4.1/§4.3):
 *
 * 1. One memory per node: content = title + body (a node is a single
 *    instruction unit, not a multi-chunk document).
 * 2. `decision_next` edges from frontmatter `edges[]` — relative targets
 *    resolved against the tree root; dangling targets skipped + logged.
 * 3. `folder_hierarchy` edges from nesting — hub(parent folder) →
 *    hub(child folder), attached to the hub node's chunk.
 *
 * Never throws on fs or index problems: edge resolution degrades, the node
 * memory is still produced.
 */
@Injectable()
export class AgentPersonaChunkingStrategy implements BaseChunkingStrategy {
  constructor(private readonly logger: BasePinoLogger) {}

  async chunkFile(
    content: string,
    filePath: string,
    sourceId: string,
    sourceConfig: WatchSourceConfig,
    _options?: ChunkFileOptions,
  ): Promise<Result<ContentChunk[]>> {
    const treeRoot = path.resolve(sourceConfig.path);
    const selfPath = path.resolve(filePath);
    const { frontmatter, body } = splitFrontmatter(content);
    const meta = extractPersonaNodeMetadata(frontmatter, filePath);

    const fileIndex = await this.listFilesSafe(treeRoot);

    const decisionEdges = buildPersonaDecisionEdges(meta, treeRoot, selfPath, fileIndex);
    this.logDanglingTargets(meta, treeRoot, selfPath, fileIndex, decisionEdges);

    const hierarchyEdges = this.folderHierarchyEdgesFor(treeRoot, fileIndex, selfPath);
    const edges = [...decisionEdges, ...hierarchyEdges];

    const chunkResult = ContentChunk.of({
      id: generateId(),
      text: `${meta.title}\n${body.trim()}`,
      chunkIndex: 0,
      totalChunks: 1,
      sectionHeader: meta.title,
      breadcrumb: filePath,
      fileRole: FILE_ROLES.DOCS,
      oversized: false,
      metadata: {
        filePath,
        sourceId,
        ...formatPersonaNodeMetadata(meta),
      },
      importance: 0.9,
      tags: ['persona-node', meta.nodeId],
      memoryBank: 'default',
      ...(edges.length > 0 && { edges }),
    });

    if (chunkResult.isKo()) {
      return chunkResult;
    }
    return Result.ok([chunkResult.getValue()]);
  }

  /** Dangling decision_next targets are skipped — but visible in the log. */
  private logDanglingTargets(
    meta: PersonaNodeMetadata,
    treeRoot: string,
    selfPath: string,
    fileIndex: string[],
    decisionEdges: FileEdge[],
  ): void {
    if (meta.edges.length === 0 || fileIndex.length === 0) {
      return;
    }
    const index = new Set(fileIndex.map(f => path.resolve(f)));
    const emitted = new Set(decisionEdges.map(e => e.target_path));
    for (const edge of meta.edges) {
      const resolved = path.resolve(treeRoot, edge.target);
      if (resolved !== path.resolve(selfPath) && !index.has(resolved) && !emitted.has(resolved)) {
        this.logger.debug(`Skipping dangling decision_next target: "${edge.target}" (node="${meta.nodeId}")`);
      }
    }
  }

  /** The folder_hierarchy edges owned by this file: only when it is a folder hub. */
  private folderHierarchyEdgesFor(treeRoot: string, fileIndex: string[], selfPath: string): FileEdge[] {
    if (fileIndex.length === 0) {
      return [];
    }
    const root = buildFolderTree(treeRoot, fileIndex);
    if (root === null) {
      return [];
    }

    const findHub = (node: FolderNode): FolderNode | null => {
      if (node.hub === selfPath) {
        return node;
      }
      for (const child of node.children) {
        const found = findHub(child);
        if (found !== null) {
          return found;
        }
      }
      return null;
    };

    const hubNode = findHub(root);
    if (hubNode === null) {
      return [];
    }
    return hubNode.children.map(child => hierarchyEdge(hubNode.hub, child));
  }

  /** Bounded recursive walk of the persona tree; fs errors degrade to []. */
  private async listFilesSafe(treeRoot: string): Promise<string[]> {
    const files: string[] = [];
    const walk = async (dir: string, depth: number): Promise<void> => {
      if (depth > MAX_WALK_DEPTH || files.length >= MAX_WALK_FILES) {
        return;
      }
      const entries = await fsp.readdir(dir, { withFileTypes: true });
      for (const entry of entries) {
        if (files.length >= MAX_WALK_FILES) {
          return;
        }
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          await walk(fullPath, depth + 1);
        } else if (entry.isFile()) {
          files.push(fullPath);
        }
      }
    };

    try {
      await walk(treeRoot, 0);
      return files;
    } catch (error) {
      this.logger.debug('Persona tree walk failed; edge resolution degrades', {
        treeRoot,
        error: String(error),
      });
      return [];
    }
  }
}
