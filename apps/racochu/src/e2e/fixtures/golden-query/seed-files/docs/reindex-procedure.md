# One-Time Reindex Procedure

After switching the embedding model (e.g. from 384-dim to 2560-dim),
all existing memories must be reindexed with the new embedding model.

## Procedure

1. **Backup** (optional — use --no-backup to skip):
   ```bash
   mnemosyne reindex --backup
   ```

2. **Reindex with no backup** (faster, destructive):
   ```bash
   mnemosyne reindex --no-backup
   ```

3. **Verify**: Run mnemosyne doctor to confirm the new dimension (2560)
   is active and all memories are re-embedded.

## Important

- The --no-backup flag skips creating a backup of the old embeddings.
- Use this when switching from 384-dim to 2560-dim (Qwen3-Embedding-4B).
- The reindex process may take several minutes depending on memory count.
- Do NOT run reindex while the chunker is actively writing — stop it first.
