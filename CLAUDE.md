# ToolGraph - notes for Claude Code

ToolGraph builds a Relate graph of an agent's own toolbox (MCP servers, tools, skills, plugins,
hooks, CLAUDE.md files, projects) and answers route / blast-radius / audit / minimal-context
questions over it. Built for the Relate x Neo4j hackathon.

## Ground rules
- Python 3.11+, `relate-db` (import `relate`). Docs for agents: https://relatedb.ai/docs/llms.txt
- The committed store is a single file: `data/toolgraph.rl`, rebuilt by `toolgraph ingest --fixtures`.
  Keep it small (well under a few MB): never commit a store built with `--embed` or from a real machine.
- One writer at a time. Ingest finishes and closes before anything reads; readers open `read_only=True`.
  A `.rl` file cannot be opened read-only while a writer holds it.
- Relate connections are single-thread: open, use, close. The MCP server opens per call.
- Cypher parameters are always `$name` params, never string-interpolated. Named queries live in
  `src/toolgraph/cypher/*.cypher`; load them with `db.cypher(name)`.
- Ingest writes with one `UNWIND $batch` per node/edge type in one transaction, MERGE on stable keys.
- Entity inference is deterministic (`entities.py`): no models, no API keys on the default path.
  `--embed hash|fastembed` is opt-in.
- Every feature needs a pytest (`python -m pytest -q`); tests run on the fixtures only.
- The README follows the hackathon template; keep its commands and sample output accurate
  (re-run `toolgraph demo` after changing queries and paste fresh output).

## Layout
- `src/toolgraph/discover.py`: reads ~/.claude.json, settings.json hooks, skills, plugins, projects
- `src/toolgraph/entities.py`: param-name -> entity (CONSUMES), "Returns ..." -> entity (PRODUCES)
- `src/toolgraph/ingest.py`: rows -> graph; computes OVERLAPS_WITH
- `src/toolgraph/queries.py` + `cypher/`: route, blast_radius, audit, minimal_context
- `src/toolgraph/mcp_server.py`: MCP tools route_tools, blast_radius, audit_toolbox, find_tools, read_cypher
- `fixtures/servers/*.json`: tools/list snapshots; `fixtures/home/`: a fake home directory
