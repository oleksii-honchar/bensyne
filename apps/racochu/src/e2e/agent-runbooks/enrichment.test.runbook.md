# Agent e2e test

Test manually all the bensyne and racochu functionality - use mcp tools, do not try to call server via curl.

**MCP enforcement:** Use only Bensyne MCP tools available via `meta_search` / `meta_use` (e.g., `recallMemory`, `listMemoryBanks`). **Never curl the MCP server.**

## Enrichment Scenario

Fixtures go to `tmp/vault/` (vault sourceType) — enrichment is sourceType-agnostic.

### Test Objective

Verify end-to-end enrichment feature in racochu:
1. Does the enrichment code path actually execute?
2. Does the LLM endpoint respond?
3. Are enriched chunks actually being stored with metadata (title, keywords)?

### Prerequisites

- racochu running with enrichment enabled in config
- LLM endpoint at `https://lite-llm.lan/v1` reachable
- bensyne-dev MCP tools available

### Test Steps

#### Step 1: Check Current State

- List existing memory banks (use `listMemoryBanks`)
- Get memory stats to see current memory count

#### Step 2: Create Test File with Enrichable Content

- Create a file with clear semantic content that should be enriched in `tmp/vault/e2e-enrichment-test.md` (relative to project root)
- File should have a title-worthy topic and identifiable keywords

#### Step 3: Wait for Processing

- Wait 3 seconds for debounce + chunking + enrichment

#### Step 4: Verify Enrichment

- Recall the content using the test file's unique identifier (use `recallMemory`)
- Check if returned chunks have enriched metadata (title, keywords)
- Compare with expected enrichment

#### Step 5: Check Logs

- Check logs at `~/.local/share/racochu/logs` to verify enrichment executed (look for enrichment-related log lines)

#### Step 6: Cleanup

- Delete the test file from `tmp/vault/`
- Verify memory was cleaned up
