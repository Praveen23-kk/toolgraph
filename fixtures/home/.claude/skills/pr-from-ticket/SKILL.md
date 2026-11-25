---
name: pr-from-ticket
description: Turn a Jira ticket into a GitHub pull request. Use when the user says "open a PR for PROJ-123", "ticket to PR" or "implement this ticket".
allowed-tools: mcp__plugin_jira-flow_atlassian__getJiraIssue, mcp__github__create_branch, mcp__github__create_pull_request
---

1. Read the ticket with `mcp__plugin_jira-flow_atlassian__getJiraIssue`.
2. Create a branch named after the issue key with `mcp__github__create_branch`.
3. Commit the change with `mcp__github__push_files`.
4. Open the PR with `mcp__github__create_pull_request`, pasting the ticket summary into the body.
