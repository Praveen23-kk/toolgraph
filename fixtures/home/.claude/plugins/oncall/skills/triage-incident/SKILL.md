---
name: triage-incident
description: Triage a production incident. Use when the user says "incident", "prod is down" or "deploy broke something".
---

1. Find the error with `mcp__plugin_oncall_sentry__search_issues` and `mcp__plugin_oncall_sentry__get_issue_details`.
2. Page the owner with `mcp__pagerduty__create_incident`.
3. File a tracking issue with `mcp__github__create_issue` and post status with `mcp__slack__slack_post_message`.
