import { z } from 'zod';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';
import { ValuesType } from '../utils/values-type';

/**
 * Domain source of truth for file type classification.
 *
 * Controls chunking strategy (prose vs code vs configuration) and chunk size limits,
 * importance scoring weights, and all places a FileRole is needed.
 *
 * - CONFIG: package.json, tsconfig.json, .env, etc.
 * - CODE: .ts, .js, .tsx, .jsx, .py, .rs, etc.
 * - DOCS: .md, .txt, .rst, etc. — default for unknown extensions
 */
export const FILE_ROLES = {
  /** Configuration files — package.json, tsconfig.json, .env, etc. */
  CONFIG: 'config' as const,
  /** Source code files — .ts, .js, .tsx, .jsx, .py, .rs, etc. */
  CODE: 'code' as const,
  /** Documentation files — .md, .txt, .rst, etc. Default for unknown extensions. */
  DOCS: 'docs' as const,
} as const;

/** File type classification used for chunking strategy, importance scoring, and memory metadata. */
export type FileRole = ValuesType<typeof FILE_ROLES>;

/**
 * Relation types between files — mirrors bensyne `RelationType` (string union, not an imported enum).
 * Exported so DTOs and chunking strategies can reference the canonical set.
 */
export const FILE_RELATION_TYPES = [
  'parent_child',
  'sibling',
  'backlink',
  'folder_hierarchy',
  'cross_reference',
  'version',
  'override',
  'dependency',
  'recommendation',
] as const;

/** File relation type (mirrors bensyne RelationType values). */
export type FileRelationType = ValuesType<typeof FILE_RELATION_TYPES>;

/** A typed edge from this chunk's source file to another file. */
export const fileEdgeSchema = z.object({
  /** Vault-relative path of the target file */
  target_path: z.string().min(1),
  relation_type: z.enum(FILE_RELATION_TYPES),
  /** Edge strength (0–1); omitted ⇒ 1 */
  strength: z.number().min(0).max(1).default(1),
  description: z.string().optional(),
});

export type FileEdge = z.infer<typeof fileEdgeSchema>;

export const contentChunkSchema = z.object({
  id: z.bigint().positive(),
  text: z.string(),
  /** Zero-based position of this chunk within the document's chunk sequence */
  chunkIndex: z.number().nonnegative(),
  /** Total number of chunks the document was split into */
  totalChunks: z.number().positive(),
  /** The closest ancestor heading this chunk belongs to (e.g., "## Getting Started") */
  sectionHeader: z.string(),
  /** Path from document root to this section (e.g., "root > docs > getting-started") */
  breadcrumb: z.string(),
  /** Programming language of the file; set only for code files */
  language: z.string().optional(),
  fileRole: z.enum(Object.values(FILE_ROLES)),
  /** True when the chunk exceeds the normal size limit and may need further splitting */
  oversized: z.boolean().default(false),
  /** Starting line number in the source file */
  startLine: z.number().optional(),
  /** Ending line number in the source file */
  endLine: z.number().optional(),
  /** User-provided key-value pairs merged into this chunk */
  metadata: z.record(z.string(), z.string()).optional(),
  /** Typed edges from this chunk's source file to other files */
  edges: z.array(fileEdgeSchema).optional(),
  /** Relevance score (0.0–1.0) assigned by the importance scoring service */
  importance: z.number().min(0).max(1).default(0.5),
  /** Keywords extracted by the tag extraction service */
  tags: z.array(z.string().min(1)).max(20).default([]),
  memoryBank: z.string().min(1).default('default'),
});

export type ContentChunkProps = z.infer<typeof contentChunkSchema>;

export class ContentChunk {
  private constructor(private readonly props: ContentChunkProps) {}

  static of(props: ContentChunkProps): Result<ContentChunk> {
    const parsed = contentChunkSchema.safeParse(props);
    if (!parsed.success) {
      return Result.ko([new ErrorWithDetails('Invalid chunk data: ' + parsed.error.message, 'InvalidChunk')]);
    }
    return Result.ok(new ContentChunk(parsed.data));
  }

  toJson(): ContentChunkProps {
    return {
      id: this.props.id,
      text: this.props.text,
      chunkIndex: this.props.chunkIndex,
      totalChunks: this.props.totalChunks,
      sectionHeader: this.props.sectionHeader,
      breadcrumb: this.props.breadcrumb,
      language: this.props.language,
      fileRole: this.props.fileRole,
      oversized: this.props.oversized,
      startLine: this.props.startLine,
      endLine: this.props.endLine,
      metadata: this.props.metadata,
      ...(this.props.edges !== undefined && { edges: this.props.edges }),
      importance: this.props.importance,
      tags: [...this.props.tags],
      memoryBank: this.props.memoryBank,
    };
  }

  get id(): bigint {
    return this.props.id;
  }
  get text(): string {
    return this.props.text;
  }
  /** Zero-based position of this chunk within the document's chunk sequence */
  get chunkIndex(): number {
    return this.props.chunkIndex;
  }
  /** Total number of chunks the document was split into */
  get totalChunks(): number {
    return this.props.totalChunks;
  }
  /** The closest ancestor heading this chunk belongs to (e.g., "## Getting Started") */
  get sectionHeader(): string {
    return this.props.sectionHeader;
  }
  /** Path from document root to this section (e.g., "root > docs > getting-started") */
  get breadcrumb(): string {
    return this.props.breadcrumb;
  }
  /** Programming language of the file; set only for code files */
  get language(): string | undefined {
    return this.props.language;
  }
  get fileRole(): FileRole {
    return this.props.fileRole;
  }
  /** True when the chunk exceeds the normal size limit and may need further splitting */
  get oversized(): boolean {
    return this.props.oversized;
  }
  /** Starting line number in the source file */
  get startLine(): number | undefined {
    return this.props.startLine;
  }
  /** Ending line number in the source file */
  get endLine(): number | undefined {
    return this.props.endLine;
  }
  /** User-provided key-value pairs merged into this chunk */
  get metadata(): Record<string, string> | undefined {
    return this.props.metadata;
  }
  /** Typed edges from this chunk's source file to other files */
  get edges(): FileEdge[] | undefined {
    return this.props.edges;
  }
  /** Relevance score (0.0–1.0) assigned by the importance scoring service */
  get importance(): number {
    return this.props.importance;
  }
  /** Keywords extracted by the tag extraction service */
  get tags(): string[] {
    return this.props.tags;
  }
  get memoryBank(): string {
    return this.props.memoryBank;
  }
}
