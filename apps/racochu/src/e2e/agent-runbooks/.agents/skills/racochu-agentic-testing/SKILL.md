---
name: racochu-agentic-testing
description: |
  Execute Racochu Agentic Testing runbooks end-to-end using MCP tools in the chat session.
  Use when user asks to run agent runbooks, points to src/e2e/agent-runbooks, or mentions "agent runbook" or "agentic test".
  Also trigger on: "run the obsidian runbook", "run the enrichment runbook", "agent-based testing", "interactive e2e test".
  DO NOT trigger on "run all tests", "run e2e tests", or "test:e2e" — those are npm test commands (npm run test / npm run test:e2e).
version: '1.1'
updatedAt: '2026-08-08T21:00:00+03:00'
author: 'racochu'
status: 'production-ready'
tags: ['agentic-testing', 'agent-runbooks', 'mcp', 'racochu', 'interactive']
---

# Racochu Agentic Testing

## Role

Execute Racochu Agentic Testing runbooks end-to-end in the chat session. This skill knows the racochu dev environment, the MCP tool chain, and the runbook conventions so an agent can run them autonomously without manual setup.

**Critical distinction — two kinds of tests in racochu:**

| What user says                                                      | What to do                                         | This skill?                                |
| ------------------------------------------------------------------- | -------------------------------------------------- | ------------------------------------------ |
| "run all tests", "run tests", "run e2e tests"                       | Run `npm run test` and `npm run test:e2e`          | **NO** — these are npm commands            |
| "run agent runbooks", "run the obsidian runbook", "agentic testing" | Load this skill and execute runbooks via MCP tools | **YES** — interactive agent-driven testing |

- **Unit + e2e tests** — automated, run via `npm run test` and `npm run test:e2e`. These are regular Jest tests.
- **Agent runbook tests** — interactive, executed by the agent in the chat using MCP tools. These simulate a user interacting with the system via bensyne MCP tools.

**Position:** Standalone execution skill — invoked when user triggers agentic runbook testing (not npm tests).

**Your Outputs:**

- Runbook execution trace in the chat (step-by-step results, MCP tool calls, verification assertions)

---

## Entry Point

**Read First:**

1. `dev.yaml` — current development configuration (watch sources, enrichment, MCP settings)
2. List `src/e2e/agent-runbooks/` — discover available runbooks
3. Read the requested runbook (or all if not specified)

**Watch folder convention:**
- **Base tmp directory is relative to racochu repo root**, NOT to the skill location or agent-runbooks directory
- Absolute path: `/Users/oleksii.honchar/www/olho/racochu/tmp/` (or `$RACOCHU_ROOT/tmp/`)
- Per-source subdirectories:
  - `tmp/general/` — General markdown files (content-aware strategy)
  - `tmp/obsidian/` — Obsidian notes with frontmatter + wikilinks
  - `tmp/agent-sessions/` — Agent session markdown files

**Critical path rule:** Always resolve `tmp/` from racochu repo root. If you're in `src/e2e/agent-runbooks/`, you must `cd` to repo root first, then use `tmp/`.

---

## Workflow

### Phase 1: Setup — Ensure Development Environment

**Objective:** Confirm racochu and bensyne are running with correct config.

1. **Check dev config:** Read `dev.yaml` and verify:
   - Watch sources include `tmp/general`, `tmp/obsidian` and `tmp/agent-sessions` with correct strategies
   - MCP URL is `http://localhost:3000` (bensyne)
   - Enrichment is configured if the runbook needs it

2. **Verify bensyne is running:** Confirm MCP tools are available at `http://localhost:3000` by listing memory banks or checking a simple query. If not available, remind user to start bensyne: `/bensyne/scripts/start.sh`

3. **Verify racochu is running:** Check process count via `ps aux | rg "racochu" | wc -l`. If count > 1, the server is running (the extra lines are nodemon + node processes). If count ≤ 1, racochu is not running — remind user to start it: `npm run start:dev`.

**Tools:**

- `meta_search("memory_list_banks")` — verify bensyne MCP connectivity
- `read_file` — read `dev.yaml` and runbook
- `bash` — `ps aux | rg "racochu" | wc -l` to check racochu process count

**Output:** Confirmation that both racochu and bensyne are running with correct config.

### Phase 2: Discover Runbooks

**Objective:** List available runbooks and determine which to execute.

1. List files in `src/e2e/agent-runbooks/` matching `*.test.runbook.md`
2. If user specified a particular runbook, read only that one
3. If user did not specify, read ALL runbooks and present them:
   ```
   Available runbooks:
   1. general.test.runbook.md — General racochu + bensyne flow
   2. obsidian.test.runbook.md — Obsidian frontmatter + wikilink graph
   3. enrichment.test.runbook.md — LLM enrichment pipeline
   All will be executed.
   ```

**Output:** List of runbooks to execute (single or all).

### Phase 3: Execute Runbook Steps

**Objective:** Execute each runbook step-by-step using MCP tools.

For each runbook, execute its phases in order:

1. **Read the runbook** — parse the test steps, prerequisites, and expected outcomes

2. **Execute prerequisites** — check that preconditions are met (e.g., specific watch source configured, LLM reachable)

3. **Execute test steps sequentially** — for each step:
    - If the step involves creating test files, write them to the correct `tmp/*` subdirectory based on content type:
      - General markdown files → `tmp/general/`
      - Obsidian notes (with frontmatter, wikilinks) → `tmp/obsidian/`
      - Agent session files → `tmp/agent-sessions/`
      - Other content → use the appropriate source directory from `dev.yaml`
   - If the step involves MCP tool calls, use the MCP tools (recall, list banks, etc.) — **never curl**
   - If the step involves waiting for debounce, wait the specified time (typically 2-3 seconds)
   - If the step involves assertions, verify and report pass/fail

4. **Report results** — after each runbook, summarize:
   ```
   === [runbook-name] Result ===
   Total checks: X
   Passed: X
   Failed: Y
   ```

**Tools:**

- `write_file` — create test fixture files in `tmp/` subdirectories
- `meta_search` / `meta_use` — MCP tool calls for bensyne operations (recall, list banks, etc.)
- `read_file` — read runbook instructions

**Output:** Step-by-step execution trace with pass/fail for each assertion.

### Phase 4: Cleanup

**Objective:** Clean up test artifacts and verify memory cleanup.

1. Delete all test files created during the runbook from the `tmp/` subdirectories
2. Wait for debounce + forget (2-3 seconds)
3. Verify memories were cleaned up (recall should return 0 results for the test queries)

**Output:** Confirmation of cleanup.

### Phase 5: Final Summary

**Objective:** Consolidate results from all executed runbooks.

1. Aggregate pass/fail counts across all runbooks
2. Report any failures with details
3. Report if any setup issues were encountered

**Output:** Final test summary in the chat.

---

## Gotchas

| Anti-Pattern                             | Correction                                                                                                                                                                       |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Confusing agent runbooks with npm tests  | "Run all tests" = `npm run test` + `npm run test:e2e` (automated Jest). "Run agent runbooks" = this skill (interactive, MCP tools). Never load this skill for npm test commands. |
| Trying to curl racochu on a port         | Raco chu is NOT available via HTTP ports — it starts via `npm run start:dev` and communicates through the file system                                                            |
| Using curl to test bensyne               | bensyne MCP tools are accessed via `meta_search` / `meta_use` — never curl                                                                                                       |
| Starting bensyne via npm                 | bensyne is started via `bensyne/scripts/start.sh` (relative to workspace root), not `npm run`                                                                                    |
| Putting fixture files in wrong directory | Files must go to the correct `tmp/*` subdirectory matching the watch source: `tmp/obsidian/` for Obsidian, `tmp/agent-sessions/` for agent sessions                              |
| Not waiting for debounce                 | Always wait the specified debounce time (2-3 sec) after file creation before recalling — otherwise the chunker hasn't processed yet                                              |
| Assuming bensyne is running              | bensyne may not be running — always verify with a memory list call before proceeding                                                                                             |

---

## Watch Folder Convention

The `dev.yaml` config defines three specialized watch sources for agent testing:

```yaml
watchSources:
  - id: tmp-general
    path: ./tmp/general
    strategy: content-aware
    # ...
  - id: tmp-obsidian
    path: ./tmp/obsidian
    strategy: obsidian
    # ...
  - id: tmp-agent-sessions
    path: ./tmp/agent-sessions
    strategy: agent-sessions
    # ...
```

When creating test files during runbook execution, place them in the matching `tmp/*` subdirectory:

| Content type                                | Directory             | Watch source         | Strategy         |
| ------------------------------------------- | --------------------- | -------------------- | ---------------- |
| General markdown files                      | `tmp/general/`        | `tmp-general`        | `content-aware`  |
| Obsidian notes with frontmatter + wikilinks | `tmp/obsidian/`       | `tmp-obsidian`       | `obsidian`       |
| Agent session markdown files                | `tmp/agent-sessions/` | `tmp-agent-sessions` | `agent-sessions` |

**Why separate directories:** Each source uses a different chunking strategy and memory bank. Obsidian strategy parses frontmatter, wikilinks, and generic properties. Agent-sessions strategy extracts session metadata. Mixing them in one directory loses strategy-specific enrichment.

---

## When to Ask for Direction

Stop and ask when you encounter:

- **bensyne unreachable** — MCP tools fail after 2 retries; ask user to confirm bensyne is started
- **raco chu not running** — `ps aux | rg "racochu" | wc -l` returns ≤ 1; ask user to confirm `npm run start:dev`
- **LLM unreachable** — Enrichment runbook needs LLM at `https://lite-llm.lan/v1` but it's not responding
- **Config mismatch** — dev.yaml watch sources don't match what the runbook expects
- **Missing runbook** — Referenced runbook doesn't exist in `src/e2e/agent-runbooks/`

---

## Quality Checklist

- [ ] Confirmed this is an agent runbook request (not "run all tests" / npm test command)
- [ ] bensyne MCP tools verified accessible (memory list succeeds)
- [ ] racochu running via `npm run start:dev`
- [ ] dev.yaml watch sources include `tmp/general`, `tmp/obsidian` and `tmp/agent-sessions`
- [ ] All requested runbooks discovered and executed
- [ ] Each runbook step executed with MCP tools (not curl)
- [ ] Debounce wait times respected after file creation
- [ ] Test files placed in correct `tmp/*` subdirectory
- [ ] Assertions verified with pass/fail reporting
- [ ] Cleanup executed — test files deleted, memories forgotten
- [ ] Final summary with aggregate pass/fail counts
