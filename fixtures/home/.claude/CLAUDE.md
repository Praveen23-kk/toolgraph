# Global instructions

- Before guessing a library API, look it up with `mcp__context7__resolve-library-id` then `mcp__context7__get-library-docs`.
- Never push secrets; GitHub writes go through `mcp__github__push_files` so the gitleaks hook runs.
- Post release notes to Slack with `mcp__slack__slack_post_message`.
