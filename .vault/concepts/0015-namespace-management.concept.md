---
type: concept
system: racochu
title: "Namespace Management"
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [namespace, mnemosyne, discovery]
see_also: [concepts/0011-namespace-routing.concept.md, decisions/0029-namespace-registration-on-startup.decision.md, decisions/0030-namespace-parameter-enforcement.decision.md]
---

# Concept: Namespace Management

## What

Namespace management encompasses the lifecycle of Mnemosyne namespaces: registration with descriptions, discovery via `list_namespaces`, and enforcement of explicit namespace usage in all memory operations.

## Why

Agents need to understand what namespaces exist and what they contain. Without descriptions and explicit enforcement, agents silently default to "default" namespace, causing cross-namespace contamination.

## Key Details

**Registration:**
- RAG Content Chunker registers namespaces on startup via `register_namespace(name, description)` tool
- Config defines description per watch source: `description: "Agent session files..."`
- Registration is idempotent (safe on every startup)

**Discovery:**
- `list_namespaces` returns: name, description, memory_count
- Default namespace has hardcoded description: "Default personal memory..."

**Enforcement:**
- `namespace` parameter is REQUIRED for all memory tools (remember, recall, forget, update, sleep)
- Missing namespace → `ValidationError: namespace parameter is required`
- No implicit fallback to "default"

**Registry:**
- In-memory `NamespaceRegistry` in better-mnemosyne
- Initialized with `DEFAULT_DESCRIPTIONS` (only "default")
- RAG Content Chunker populates additional descriptions at startup
