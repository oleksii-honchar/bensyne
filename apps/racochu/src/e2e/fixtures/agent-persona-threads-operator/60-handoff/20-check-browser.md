---
id: 60-handoff-20-check-browser
title: "Check chrome-debug instance availability"
entry: false
conditions:
  - "chrome-debug instance status unknown at entry"
veto: []
edges:
  - target: 10-discovery/10-discover.md
    when: "chrome-debug on :9222 confirmed running with logged-in Threads session"
  - target: 60-handoff/10-surface-problem.md
    when: "chrome-debug instance not running — user must launch debug Chrome with Threads profile"
created: 2026-09-03
updated: 2026-09-03
status: active
---
# Check chrome-debug instance availability

**Before starting:** Record your traversal transition to this node in your session memory bank.

Verify the chrome-debug instance is running on port 9222: `curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1 && echo "RUNNING" || echo "NOT RUNNING"`. If running, verify the Threads tab exists and pageId is confirmed. If not running, surface to the user — the debug Chrome with the Threads profile must be launched first before any scraping can proceed.
