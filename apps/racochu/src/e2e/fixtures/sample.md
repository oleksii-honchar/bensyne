# Project Overview

## Introduction

This is a sample markdown document for testing racochu.
It demonstrates various markdown structures that the chunker should handle.

## Features

- Feature 1: File watching with chokidar
- Feature 2: Content-aware chunking strategies
- Feature 3: Mnemosyne MCP integration
- Feature 4: YAML configuration management

### Chunking Strategies

The chunker supports multiple strategies:

1. **Markdown** — heading-aware chunking with breadcrumb context
2. **Code** — recursive chunking respecting language syntax
3. **Config** — structure-aware chunking for JSON/YAML/TOML
4. **Text** — sentence-based chunking for plain text

## Configuration

Configure the chunker via `~/.config/racochu.yaml`.

Example configuration:

```yaml
watchSources:
  - path: ~/projects/docs
    recursive: true
```

## Getting Started

Run `npx racochu` to start the service.

The service will:
- Watch configured directories for file changes
- Apply appropriate chunking strategies based on file type
- Ingest chunks into Mnemosyne MCP for vector embedding

## API Reference

### Chunk Content

```typescript
interface ChunkRequest {
  content: string;
  filePath: string;
  sourceId: string;
  maxTokens?: number;
  overlapTokens?: number;
}
```

### Response

Each chunk includes metadata for context preservation:

- `id`: Unique chunk identifier
- `text`: Chunk content
- `sectionHeader`: Parent heading context
- `breadcrumb`: Full heading hierarchy
- `chunkIndex`: Position within source file
- `totalChunks`: Total chunks from source file
