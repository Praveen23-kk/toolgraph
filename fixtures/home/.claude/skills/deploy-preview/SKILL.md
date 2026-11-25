---
name: deploy-preview
description: Deploy a preview environment for a pull request. Use when the user says "deploy", "deploy preview" or "ship it to staging".
---

Wait until `mcp__github__get_pull_request_status` is green, run `Bash` with `make preview`,
then post the preview URL with `mcp__slack__slack_post_message`.
