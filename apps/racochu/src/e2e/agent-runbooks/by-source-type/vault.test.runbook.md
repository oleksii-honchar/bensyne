# Agent e2e test

## Vault scenario

Test manually the bensyne and racochu functionality using mcp tools — do not try to call server via curl. When waiting for debounce — wait 2 sec, no more.

**MCP enforcement:** Use only Bensyne MCP tools available via `meta_search` / `meta_use` (e.g., `recallMemory`, `listMemoryBanks`). **Never curl the MCP server.**

Fixtures go to `tmp/vault/` (vault sourceType). Use general markdown/fixtures from `src/e2e/fixtures/` (sample.md, sample.ts, sample.json, etc.).

- First check what memory you have in vault and what banks you have (use `listMemoryBanks`).
- Then copy fixture file `src/e2e/fixtures/sample.md` to `tmp/vault/e2e-test-vault.md` (relative to project root).
- Then recall (use mcp tool `recallMemory`) "chunking strategies" to verify the sample.md content was chunked and ingested.
- Then update `tmp/vault/e2e-test-vault.md`: change "Feature 1" to "Feature 1 updated"; then recall again to check if change was applied. Also check if old memory was removed.
- Then create 2 folders in `tmp/vault`, f1 and f2.
- Create new test file in `tmp/vault/f1/test.md` with sample content.
- Test recall.
- Copy this file to `tmp/vault/f2/test.md` with the same content.
- Check logs at `~/.local/share/racochu/logs` and confirm no duplicated memory created.

Then delete all files from `tmp/vault` and recall again.
