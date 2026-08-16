---
name: bensyne-specialist
description: |
  Operate the Bensyne project — run tests, start the server, debug failures, and avoid gotchas.
  Use when any agent needs to work in the Bensyne codebase: developing features, debugging tests,
  or running the MCP server locally.
  Also trigger on: "run bensyne tests", "start bensyne server", "bensyne gotcha", "bensyne python",
  "bensyne pytest", "bensyne fastmcp", "bensyne env setup", "bensyne e2e failing".
version: "1.2"
updatedAt: "2026-08-16T14:00:00+02:00"
author: "oleksii"
status: "draft"
tags: ["bensyne", "python", "operational", "mcp-server"]
---

# Bensyne Specialist

## Role

Operational guide for working in the Bensyne codebase — the multi-tenant, namespace-aware MCP server
built on mnemosyne-oss. This skill captures gotchas, project-specific experience, and operational
knowledge that lives outside the vault (vault contains architecture, ADRs, and runbooks).

**Position:** Loaded by any agent before working in Bensyne.

**Your Outputs:** None — this is a reference skill that shapes behavior.

---

## Gotchas

### Python Version — Always Use .venv

**CRITICAL:** The system Python is 3.9.6. Bensyne requires >= 3.12.

| Wrong | Right |
|---|---|
| `python3 -m pytest` | `.venv/bin/python -m pytest` |
| `python3 main.py` | `.venv/bin/python main.py` |
| `python3 -c "import foo"` | `.venv/bin/python -c "import foo"` |

Every command: prefix with `.venv/bin/python`, not `python3`. The shebang in `main.py` (`#!/usr/bin/env python3.12`) is only relevant for direct `./main.py` execution — scripts and CLI tools still need the venv path.

### Domain Layer Discipline

- **Entities are frozen dataclasses** — `dataclass(frozen=True)`. No mutation after creation.
- **Result pattern** — no domain exceptions. Every method returns `Result[T]`, not throws.
  Read `src/domain/result.py` for the pattern. Use `Result.ok(value, events=[...])` for success,
  `Result.ko(errors=[ErrorWithDetails(...)])` for failure.
- **Domain events live in Result**, not as entity properties. The event list is returned alongside
  the value in the Result.

### SQLite — ON CONFLICT DO UPDATE

Use `ON CONFLICT(id) DO UPDATE SET ...` for upserts, not `INSERT OR REPLACE`.
The `INSERT OR REPLACE` pattern deletes and re-inserts, losing foreign key references (e.g. file_chunks
orphaned on file update). This gotcha was discovered in the file metadata layer.

### FastMCP 3.x Tool Registration

Tools are registered in `src/app.py` using `@mcp.tool(name="toolName")`. The router is bound via
wrapper functions (not `functools.partial` — FastMCP generates JSON schema from function signatures).
When adding a new tool: follow the pattern in `app.py` — define the async function with explicit
typed parameters, then delegate to `handlers.handle_*()`.

---

## Entry Point

**When working in Bensyne, first check:**

1. **Which Python?** — Confirm you're using `.venv/bin/python` (not `python3`)
2. **Vault lookup** — The monorepo has a single flat vault at `.vault/` with area folders (`decisions/`, `concepts/`, `memories/`, `specifications/`, `runbooks/`, `architectures/<system>/`; `.vault/_Vault-Home.md` documents the layout). Check the vault before asking:
   - Scope nodes by the `system` frontmatter field: `shared | bensyne-mcp | racochu`
   - ID series: `DEC-NNNN` (decisions), `MEM-NNNN` (shared memories only)
3. **Test boundaries** — Domain: `test_domain/`, Infra: `test_infrastructure/`, App: `test_application/`, Integration: `integration/`.

---

## Workflow

### Phase 1: Environment Setup

**Goal:** Verify you can run the project.

1. Confirm `.venv` exists: `ls .venv/bin/python`
2. Run a quick smoke test: `.venv/bin/python -m pytest src/tests/test_domain/test_file.py -v --tb=short`
3. If tests fail with `SyntaxError: invalid syntax` — you're using the system Python 3.9. Switch to `.venv/bin/python`.

**Output:** Confirmed Python version and test runner works.

### Phase 2: Run the Right Tests

**Goal:** Verify your changes don't break existing functionality.

Run the full suite scoped to the affected layer:

```bash
# Domain changes — run domain tests
.venv/bin/python -m pytest src/tests/test_domain/ -v --tb=short

# Infrastructure changes — run infra tests
.venv/bin/python -m pytest src/tests/test_infrastructure/ -v --tb=short

# Application changes — run app tests
.venv/bin/python -m pytest src/tests/test_application/ -v --tb=short

# Integration changes — run integration tests
.venv/bin/python -m pytest src/tests/integration/ -v --tb=short

# Full suite (skipping e2e)
.venv/bin/python -m pytest --ignore=src/tests/e2e/ -v --tb=short
```

**Output:** Test results. If e2e errors appear, verify they're the pre-existing `bank_manager` issue.

### Phase 3: Start the Server

**Goal:** Verify the server runs with your changes.

```bash
# Copy .env from template if needed
cp .env.tpl .env

# Start server
.venv/bin/python main.py
```

The server loads `.env` via `load_dotenv` (or manual parsing if dotenv is missing).

**Output:** Server running on the configured port.

### Phase 4: Debug a Failure

**Goal:** Diagnose a test or runtime failure.

1. **Identify the layer** — domain, infrastructure, application, or integration
2. **Run isolated tests** — target the specific test file with `-v --tb=long`
3. **Check for domain violations** — if a test expects an exception but the code uses Result, or vice versa
4. **Check for frozen dataclass issues** — if mutation fails, the entity is frozen (by design)
5. **Check for foreign key issues** — if SQLite integrity errors appear on update, check for `INSERT OR REPLACE` instead of `ON CONFLICT DO UPDATE`

**Output:** Root cause identified and fix applied.

---

## When to Ask for Direction

Stop and ask when you encounter:
- **Domain violation** — codebase uses exceptions in a place where Result should be used (or vice versa)
- **E2E failure outside the known bank_manager issue** — could indicate a real regression
- **New entity or aggregate needed** — architectural decision that should go through the vault
- **SQLite schema change** — migration implications across repositories
- **Foreign key cascade** — delete/update cascades in SQLite (use `ON CONFLICT DO UPDATE` pattern)

---

## Quality Checklist

- [ ] Used `.venv/bin/python` (not `python3`) for all commands
- [ ] Ran tests scoped to the affected layer (not just full suite)
- [ ] Domain changes: entities are frozen, Result pattern used, no domain exceptions
- [ ] Infrastructure changes: `ON CONFLICT DO UPDATE` used for upserts (not `INSERT OR REPLACE`)
- [ ] New tools registered in `app.py` following the handler pattern
- [ ] Checked the flat vault (`.vault/` — scope by `system` frontmatter: `shared | bensyne-mcp | racochu`) for relevant architecture before making design decisions
- [ ] No TODO/FIXME left behind

---

## Shared Patterns / References

- `.vault/` — Single flat monorepo vault, the single source of architectural knowledge for the whole monorepo: decisions, concepts, memories, runbooks, specs, C4 architectures.
  - Area folders: `decisions/`, `concepts/`, `memories/`, `specifications/`, `runbooks/`, `architectures/<system>/` (per-system C4)
  - Scope by the `system` frontmatter field: `shared | bensyne-mcp | racochu` — flat areas stay flat, no per-system sub-vaults
  - ID series: `DEC-NNNN` (decisions), `MEM-NNNN` (shared memories only)
  - `.vault/_Vault-Home.md` — documents the layout. Read when you need architectural context.
- `src/domain/result.py` — Result pattern with domain events. Read when implementing domain methods.
- `src/app.py` — Tool registration pattern. Read when adding new MCP tools.
- `src/domain/interfaces.py` — Repository interfaces. Read when implementing a new domain entity.
- `src/services/tools/handlers.py` — Handler functions. Read when debugging tool calls.
