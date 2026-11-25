---
name: docs-lookup
description: Look up current library documentation. Use when the user says "check the docs", "how do I use" or "latest API".
---

Resolve with `mcp__context7__resolve-library-id`, read with `mcp__context7__get-library-docs`.
If the library is not indexed, fall back to `mcp__fetch__fetch` on the official docs URL.
