---
id: 10-discovery-20-navigate-profile
title: "Navigate to profile feed, locate target post"
entry: false
conditions:
  - "target handle is known and chrome-debug instance confirmed running with authenticated session"
veto:
  - "proceeding without verifying the debug Chrome has an authenticated Threads session (login wall)"
  - "navigating a non-Threads URL"
edges:
  - target: 20-open-post/10-open-post.md
    when: "target post identified on profile feed with root ID and part count"
  - target: 60-handoff/10-surface-problem.md
    when: "post not found on the visible portion of the feed (may require user to provide direct URL)"
created: 2026-09-03
updated: 2026-09-03
status: active
---
# Navigate to profile feed, locate target post

**Before starting:** Record your traversal transition to this node in your session memory bank.

Navigate to `https://www.threads.net/@<handle>` using the chrome-debug instance (pageId from navigator). Sleep 3 seconds for render. Take a snapshot to identify the target post — look for author name matching handle, the post text excerpt, and the N / M part counter badge. Record the root post ID for navigation. If the feed truncation hides the target ("View N more"), request the direct post URL from the user or surface this limitation.
