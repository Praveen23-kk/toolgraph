---
name: release-deploy
description: Cut a production release. Use when the user says "deploy", "release" or "ship it".
---

1. Merge the release PR with `mcp__github__merge_pull_request`.
2. Move the Linear ticket to Done with `mcp__linear__update_issue`.
3. Announce in #releases with `mcp__slack__slack_post_message`.
