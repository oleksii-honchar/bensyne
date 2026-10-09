---
type: decision
id: DEC-0117
title: "Cleanup Cron — Deployment-Local Log Path + Fail-Loud No-Op Detection"
status: accepted
createdAt: "2026-10-08T20:33:16Z"
updatedAt: "2026-10-08T20:33:16Z"
tags: [bensyne-mcp, cleanup, cron, observability, deployment]
system: bensyne-mcp
supersedes: []
superseded_by: []
see_also:
  - "decisions/0111-ephemeral-session-bank-cleanup.decision.md"
  - "decisions/0115-session-bank-regex-mixed-case.decision.md"
  - "decisions/0116-session-bank-age-durable-signal.decision.md"
  - "runbooks/0010-session-bank-cleanup-verification.runbook.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0117: Cleanup Cron — Deployment-Local Log Path + Fail-Loud No-Op Detection

## Context

Two independent silent failures hid the broken cleanup for weeks: (1) the crontab entry redirected to `/var/log/bensyne-cleanup.log`, not writable by the deploying user — the shell aborted before the script ever ran (journalctl showed the job firing daily with no effect); (2) once the endpoint did run, HTTP 200 + `banks_matched: 0` looked like success — nothing consumed the report counts.

## Decision

Combined hardening of the two cron scripts (`puma-lan/lite-llm/mcp/bensyne/`):
- **Log path (session DEC-A3):** `setup-cron.sh` uses `CRON_LOG="${SCRIPT_DIR}/logs/bensyne-cleanup.log"` (deployment-local, always writable by the deploying user); `install` runs `mkdir -p`; `cron-cleanup-banks.sh` default aligned (keeps `BENSYNE_LOG_FILE` override). Deployment re-runs `./setup-cron.sh install` (idempotent).
- **Fail-loud (session DEC-A4):** after HTTP 200, if `"banks_matched": 0` while `"banks_scanned" > 0` → log WARNING and `exit 2` (cron surfaces non-zero exits); matched > 0 but eligible == 0 in execute mode → WARNING, exit 0 (policy, not error). Parsed with grep/sed only — no jq dependency on puma.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| `/var/log` via root's crontab | System-standard | Needs root; moves job off deploying user | Ops burden, breaks user-owned install |
| `~/logs/` or `~/.local/state/` | Writable | Assumes a home layout | Deployment dir (`SCRIPT_DIR`) is the known anchor |
| `/tmp` (old script default) | Zero setup | Wiped on reboot | Not durable enough for an audit trail |
| systemd timer | Journal for free | New mechanism on puma | Overkill for this repair |
| Server-side alerting | Centralized | New coupling for a once-a-day job | Over-engineered |
| jq-based parsing | Robust JSON | jq not confirmed on puma | Portability |
| Keep silent success | No change | Exactly the failure mode that hid the bug | Status quo rejected |

## Consequences

- **Positive:** Job actually executes daily; log survives reboots; regex/age regressions become visible within 24h.
- **Negative:** False alarm possible if all banks are legitimately young — warning text distinguishes matched==0 (suspect) from eligible==0 (policy).
- **Neutral:** Log rotation remains manual (acceptable at current volume).
