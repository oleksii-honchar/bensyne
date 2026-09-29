---
id: 10-discovery-10-discover
title: "Discovery — find post on profile feed or navigate directly"
entry: false
conditions:
  - "target handle (e.g. @username) or post URL is known"
  - "chrome-debug debug Chrome instance running on :9222 with logged-in Threads session"
veto:
  - "navigating to a non-Threads URL"
  - "continuing without verifying the debug Chrome has the user's authenticated session (login wall risk)"
edges:
  - target: 10-discovery/20-navigate-profile.md
    when: "only handle is known — need to find the post on the profile feed"
  - target: 20-open-post/10-open-post.md
    when: "full post URL is already known (user provided or resolved from prior session)"
created: 2026-09-03
updated: 2026-09-03
status: active
---
# Discovery — find post on profile feed or navigate directly

**Before starting:** Record your traversal transition to this node in your session memory bank.

Navigate to the Threads profile URL (`https://www.threads.net/@<handle>`), wait 3 seconds for render, then take a snapshot of the feed. Identify the target post by root ID and part count (N / M badge). Feed may truncate long threads behind "View N more" — discovery is for identifying posts and their part counts, NOT for reading. If the post was already linked directly, proceed to open-post.
