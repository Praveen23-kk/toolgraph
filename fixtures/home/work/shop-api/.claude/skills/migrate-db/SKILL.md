---
name: migrate-db
description: Write and apply a database migration. Use when the user says "migration", "add a column" or "deploy the schema".
---

Inspect the current schema with `mcp__postgres__query`, write the migration file with
`mcp__filesystem__write_file`, and apply it with `Bash`.
