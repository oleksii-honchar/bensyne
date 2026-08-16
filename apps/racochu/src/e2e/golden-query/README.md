# Golden-Query Validation

Retrieval-quality regression harness for racochu → Mnemosyne. Validates that
switching the embedding model (bge-small → Qwen3-Embedding-4B via LiteLLM) and
bumping chunk sizes (ADR-0054) do not regress retrieval.

## Metrics

- **Recall@5** — relevant hits in top-5 / total relevant
- **Precision@5** — relevant hits in top-5 / 5
- **MRR** — 1 / rank of first relevant hit

**Blocking rule (ADR-0055):** an MRR drop > 10% (absolute) versus baseline is
**blocking** — do not flip the default embedding matrix without review.

## Layout

| File | Purpose |
|---|---|
| `src/e2e/fixtures/golden-query/corpus.ts` | Data fixture — 20 deterministic queries (5 per type: prose/code/configuration/documentation) |
| `src/e2e/fixtures/golden-query/seed.ts` | Loader — reads seed files from `seed-files/` (no JSON encoding) |
| `src/e2e/fixtures/golden-query/seed-files/` | 20 actual files (prose/code/config/docs) to seed the watch directory |
| `src/e2e/golden-query/corpus.test.ts` | Validates fixture structure (count, coverage, unique ids) |
| `src/e2e/golden-query/metrics.ts` | Pure metric functions: Recall@5, Precision@5, MRR, aggregation, deltas |
| `src/e2e/golden-query/metrics.test.ts` | Unit tests for metric math (19 tests) |
| `src/e2e/golden-query/runner.ts` | Scoring + aggregation + report generation + blocking logic |
| `src/e2e/golden-query/runner.test.ts` | Unit tests for runner helpers and aggregation (12 tests) |
| `src/e2e/golden-query/expected-content.ts` | Maps corpus memory keys to expected content snippets |
| `src/e2e/golden-query/golden-query.test.ts` | Live e2e run against Mnemosyne via the Docker stack |
| `src/e2e/golden-query/reports/` | Generated JSON reports (e.g. `baseline-report.json`) |

## Prerequisites

- bensyne (Mnemosyne MCP) reachable — the e2e `global-setup.ts` starts the
  Docker stack (`docker compose -f src/e2e/env-setup/docker-compose.bensyne.yml`)
- `MNEMOSYNE_EMBEDDING_*` env vars set (model `puma-embed-qwen3-4b`,
  API URL, API key, `MNEMOSYNE_EMBEDDING_DIM=2560`)
- LiteLLM gateway + llama-swap up (see runbook for health checks)

## Run

```bash
# Unit tests for corpus + metrics + runner math (no infra required)
npm run golden-query:unit

# Live e2e run against Mnemosyne (writes reports/baseline-report.json)
npm run golden-query
```

## Comparing runs

The runner supports a `baseline` option that computes deltas and sets the
`mrrDropBlocking` flag when MRR drops > 0.10 below baseline:

1. Run baseline → `reports/baseline-report.json`
2. Reindex with new embedding (if switching models)
3. Re-run with `baseline` option → runner computes deltas + blocking flag
4. If `mrrDropBlocking` is `true`, the switch is blocked pending review
