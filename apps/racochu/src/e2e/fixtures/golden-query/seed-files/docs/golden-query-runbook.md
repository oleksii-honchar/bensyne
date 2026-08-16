# Golden-Query Regression Suite

## Purpose

The golden-query suite validates retrieval quality after changes to the
embedding model, chunking strategies, or Mnemosyne configuration. It runs
a fixed corpus of queries against Mnemosyne recall and scores Recall@5,
Precision@5, and MRR.

## How to Run

Run the golden-query regression suite after any retrieval-related change:

```bash
npm run golden-query
```

This executes the full corpus through Mnemosyne recall and writes a
JSON report to src/e2e/golden-query/reports/baseline-report.json.

## Metrics

- **Recall@5**: Fraction of relevant items found in top-5 results
- **Precision@5**: Fraction of top-5 results that are relevant
- **MRR**: Mean Reciprocal Rank — how quickly the first relevant item appears

## Regression Guard

If a baseline report exists, the runner compares MRR against it. A drop
of more than 10% triggers a blocking flag (mrrDropBlocking: true).
