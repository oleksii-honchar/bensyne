---
type: runbook
title: "Production Deployment"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [production, deployment]
see_also: ["concepts/0004-namespace-routing.concept.md"]
---

# Runbook: Production Deployment

## Goal

Deploy RAG Content Chunker as a production service watching configured sources.

## Prerequisites

- Node.js >= 26.0.0
- Remote Mnemosyne MCP server (better-mnemosyne) accessible
- Config file location writable: `~/.config/rag-content-chunker.yaml`

## Steps

1. **Create config:**
   ```bash
   cp .env.tpl ~/.config/rag-content-chunker.yaml
   ```
   Configure watch sources with namespaces:
   ```yaml
   watchSources:
     - id: agent-sessions
       path: ~/.agent-sessions
       namespace: agent-sessions
     - id: vault-knowledge
       path: ~/.vault
       namespace: vault
   mcp:
     url: https://your-mnemosyne-server.lan/mcp/mnemosyne
     apiKey: your-token
   ```

2. **Build:**
   ```bash
   npm install
   npm run build
   ```

3. **Run:**
   ```bash
   npm run start:prod
   ```
   Or via npx:
   ```bash
   npx rag-content-chunker
   ```

## Verification

- Check logs: `~/.local/share/rag-content-chunker/logs/current.log`
- Verify Mnemosyne connectivity: watch a file change, check ingestion logs
- Monitor queue: logs show "File processed: ... chunks=N"

## Rollback

- Stop: SIGTERM (graceful drain) or SIGINT
- Restore config: backup before editing
