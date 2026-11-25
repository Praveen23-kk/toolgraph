"""ToolGraph as an MCP server (stdio), so an agent can query its own toolbox.

    claude mcp add toolgraph -- toolgraph serve --database /abs/path/data/toolgraph.rl

Every call opens the store read-only, answers, and closes it (Relate connections are
single-thread, and nothing here writes).
"""
from __future__ import annotations

import json

from toolgraph import db, queries
from toolgraph.embed import stored_embedder
from toolgraph.render import blast_mermaid, route_mermaid

READ_ONLY_PREFIXES = ("MATCH", "OPTIONAL", "WITH", "UNWIND", "RETURN", "CALL", "SHOW", "EXPLAIN", "PROFILE")


def build_server(database: str):
    try:  # mcp >= 2
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server

    app = Server("toolgraph", instructions=(
        "ToolGraph is a graph of this agent's own toolbox: MCP servers, tools, skills, plugins, hooks, "
        "projects and the entities tools consume and produce. Use route_tools before a multi-tool task, "
        "find_tools to pick a small set of tools for a goal, blast_radius before removing a server, and "
        "audit_toolbox to find broken skills, dead hooks and duplicate tools."))

    def _run(fn, *a, **kw):
        with db.open_store(database, read_only=True) as conn:
            return fn(conn, *a, **kw)

    @app.tool()
    def route_tools(goal: str = "", to_entity: str = "", from_entity: str = "",
                    have: list[str] | None = None, project: str = "") -> str:
        """Order the tools that achieve a goal, e.g. "open a PR on my repo from a Jira ticket".
        Entities (optional, override the goal parse): pull_request, jira_issue, branch, repository,
        file_path, sentry_issue, slack_channel, url, ... Returns JSON with steps and a mermaid diagram."""
        r = _run(queries.route, to=to_entity or None, src=from_entity or None, have=have or [],
                 goal=goal or None, project=project or None)
        r["mermaid"] = route_mermaid(r)
        return json.dumps(r, indent=1)

    @app.tool()
    def blast_radius(server: str) -> str:
        """What breaks if an MCP server is removed: lost tools, broken/degraded skills, hooks,
        CLAUDE.md files, projects, and entities nothing else can produce."""
        b = _run(queries.blast_radius, server)
        b["mermaid"] = blast_mermaid(b)
        return json.dumps(b, indent=1)

    @app.tool()
    def audit_toolbox() -> str:
        """Skills that reference uninstalled tools, hooks that match nothing, skills that collide on
        the same trigger phrase, duplicate tools across servers, and unused servers."""
        return json.dumps(_run(queries.audit), indent=1)

    @app.tool()
    def find_tools(goal: str, k: int = 8, project: str = "") -> str:
        """The k tools worth loading for a goal (route + skills + search + graph neighbours),
        with the context tokens saved versus loading every tool."""
        def go(conn):
            return queries.minimal_context(conn, goal, k=k, project=project or None, embed=stored_embedder(conn))
        return json.dumps(_run(go), indent=1)

    @app.tool()
    def read_cypher(query: str, params: dict | None = None) -> str:
        """Run a read-only Cypher query against the toolbox graph (labels: Agent, Server, Tool, Entity,
        Skill, Keyword, Hook, Plugin, Project, Instruction)."""
        if not query.lstrip().upper().startswith(READ_ONLY_PREFIXES):
            return json.dumps({"error": "read queries only"})
        return json.dumps(_run(lambda c: db.rows(c, query, params or {})), indent=1, default=str)

    return app


def serve(database: str) -> None:
    build_server(database).run()
