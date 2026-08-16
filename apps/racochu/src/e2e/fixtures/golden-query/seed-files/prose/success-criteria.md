# RAG Content Chunker — Success Criteria

The following success criteria define when the RAG content chunker tool
is considered complete and production-ready:

1. The server starts with the npx command and watches configured directories.
2. Content-aware chunking strategies are implemented for markdown, code,
   config, and plain text files.
3. Chunks are properly formatted for Mnemosyne MCP ingestion with metadata.
4. The tool follows DDD patterns with Result types and no exceptions.
5. Chunking is configurable per watch source with per-type character limits.

The RAG content chunker must demonstrate reliable chunking across all
supported content types with no data loss or corruption.
