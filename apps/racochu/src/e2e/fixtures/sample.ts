// Sample TypeScript file for e2e chunking tests
// This file is read as content — not compiled as part of the project

export interface ChunkRequest {
  content: string;
  filePath: string;
  sourceId: string;
  maxTokens?: number;
  overlapTokens?: number;
  hardCapTokens?: number;
}

export interface ChunkMetadata {
  filePath?: string;
  sourceId?: string;
  language?: string;
}

export class ContentChunkerService {
  private readonly DEFAULT_MAX_TOKENS = 512;
  private readonly DEFAULT_OVERLAP = 50;

  async chunkContent(request: ChunkRequest): Promise<string[]> {
    if (!request.content || request.content.trim().length === 0) {
      throw new Error('Content is required');
    }

    if (!request.filePath) {
      throw new Error('File path is required');
    }

    const chunker = this.determineChunker(request.filePath);
    return chunker.chunk(request.content, {
      maxTokens: request.maxTokens ?? this.DEFAULT_MAX_TOKENS,
      overlapTokens: request.overlapTokens ?? this.DEFAULT_OVERLAP,
      hardCapTokens: request.hardCapTokens,
      metadata: {
        filePath: request.filePath,
        sourceId: request.sourceId,
      },
    });
  }

  private determineChunker(filePath: string): ChunkingStrategy {
    const ext = this.getExtension(filePath).toLowerCase();

    if (ext === '.md' || ext === '.mdx') {
      return { name: 'markdown', chunk: () => [] };
    }

    if (['.ts', '.tsx', '.js', '.jsx', '.py', '.go'].includes(ext)) {
      return { name: 'code', chunk: () => [] };
    }

    if (['.json', '.yml', '.yaml', '.toml'].includes(ext)) {
      return { name: 'config', chunk: () => [] };
    }

    return { name: 'text', chunk: () => [] };
  }

  private getExtension(filePath: string): string {
    const parts = filePath.split('.');
    return parts.length > 1 ? `.${parts[parts.length - 1]}` : '';
  }
}

interface ChunkingStrategy {
  name: string;
  chunk(content: string, options: ChunkOptions): string[];
}

interface ChunkOptions {
  maxTokens: number;
  overlapTokens: number;
  hardCapTokens?: number;
  metadata?: ChunkMetadata;
}
