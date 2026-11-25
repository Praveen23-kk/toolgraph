# shop-api

Postgres is the source of truth. Inspect data with `mcp__postgres__query` (read-only).
Schema changes are migrations under `migrations/`; write them with `mcp__filesystem__write_file`.
