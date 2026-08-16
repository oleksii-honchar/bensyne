---
type: runbook
system: racochu
title: "Local Development Setup"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [development, setup]
see_also: []
---

# Runbook: Local Development Setup

## Goal

Set up RAG Content Chunker for local development with Docker-based Mnemosyne MCP.

## Prerequisites

- Node.js >= 26.0.0
- npm >= 11.0.0
- Docker and Docker Compose

## Steps

1. **Clone and install:**
   ```bash
   cd /Users/oleksii.honchar/www/olho/rag-content-chunker
   npm install
   ```

2. **Start Mnemosyne MCP (Docker):**
   ```bash
   npm run mnemosyne:start
   ```
   - Endpoint: http://localhost:8765
   - Token: e2e-test-token
   - Data: ./data/e2e

3. **Start the chunker:**
   ```bash
   npm run start:dev
   ```
   - Uses dev.yaml config
   - Watches ./watch-folder-dev

4. **Test:** Drop files into `./watch-folder-dev/` — they are auto-chunked and ingested.

## Verification

- Logs: `npm run start:dev` output (pretty-printed in dev mode)
- Mnemosyne logs: `npm run mnemosyne:logs`
- Test ingestion: `npm run test:e2e`

## Rollback

```bash
npm run mnemosyne:stop
```
