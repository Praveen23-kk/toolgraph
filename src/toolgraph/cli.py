"""toolgraph CLI: ingest, ask, route, blast, audit, context, capture, serve, stats."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from toolgraph import __version__, db, queries, render

REPO = Path(__file__).resolve().parents[2]
FIXTURE_HOME = REPO / "fixtures" / "home"
FIXTURE_SCHEMAS = REPO / "fixtures" / "servers"
CACHE_SCHEMAS = Path.home() / ".toolgraph" / "servers"


def _emit(args, data: dict, text_fn, mermaid_fn=None) -> None:
    if args.json:
        print(json.dumps(data, indent=1, default=str))
    elif getattr(args, "mermaid", False) and mermaid_fn:
        print(mermaid_fn(data))
    else:
        print(text_fn(data))


def _read(args):
    return db.open_store(args.database, read_only=True)


def cmd_ingest(args) -> int:
    from toolgraph.discover import discover
    from toolgraph.ingest import ingest

    if args.fixtures:
        home, schemas = FIXTURE_HOME, FIXTURE_SCHEMAS
    else:
        home = Path(args.home).expanduser()
        schemas = Path(args.schemas).expanduser() if args.schemas else CACHE_SCHEMAS
    box = discover(home, schemas)
    counts = ingest(box, args.database)
    if args.embed:
        from toolgraph.embed import add_vectors, get_embedder
        with db.open_store(args.database) as conn:
            counts["embedded"] = add_vectors(conn, get_embedder(args.embed))
    no_schema = [s.id for s in box.servers.values() if not s.has_schema]
    if args.json:
        print(json.dumps({"database": args.database, "counts": counts, "no_schema": no_schema}, indent=1))
        return 0
    print(f"ingested {'fixtures' if args.fixtures else home} -> {args.database}")
    print("  " + ", ".join(f"{k}={v}" for k, v in counts.items() if v))
    if no_schema:
        print(f"  {len(no_schema)} server(s) have no tool list yet: {', '.join(no_schema)}")
        print("  run `toolgraph capture` to fetch them, then ingest again")
    return 0


def cmd_route(args) -> int:
    with _read(args) as conn:
        r = queries.route(conn, to=args.to, src=args.src, have=args.have, goal=args.goal, project=args.project)
    _emit(args, r, render.route_text, render.route_mermaid)
    return 0 if r.get("steps") else 1


def cmd_blast(args) -> int:
    with _read(args) as conn:
        b = queries.blast_radius(conn, args.server)
    _emit(args, b, render.blast_text, render.blast_mermaid)
    return 1 if "error" in b else 0


def cmd_audit(args) -> int:
    with _read(args) as conn:
        a = queries.audit(conn)
    _emit(args, a, render.audit_text)
    return 2 if getattr(args, "strict", False) and (a["dangling"] or a["dead_hooks"]) else 0


def cmd_context(args) -> int:
    from toolgraph.embed import stored_embedder
    with _read(args) as conn:
        c = queries.minimal_context(conn, args.goal, k=args.k, project=args.project, embed=stored_embedder(conn))
    _emit(args, c, render.context_text)
    return 0


def cmd_ask(args) -> int:
    """One entry point for plain-English questions; picks the question type from the wording."""
    q = args.question.strip()
    low = q.lower()
    for word in ("remove ", "uninstall ", "drop ", "delete ", "without "):
        if word in low:
            with _read(args) as conn:
                names = [r["id"] for r in db.rows(conn, "MATCH (s:Server) RETURN s.id AS id")]
            hit = next((n for n in sorted(names, key=len, reverse=True)
                        if n.lower() in low or n.lower().replace("plugin_", "").split("_")[-1] in low), None)
            if hit:
                args.server = hit
                return cmd_blast(args)
    if any(w in low for w in ("audit", "broken", "dangling", "collide", "collision", "duplicate", "unused")):
        return cmd_audit(args)
    if any(w in low for w in ("which tools", "what tools", "load", "context", "minimal")):
        args.goal = q
        return cmd_context(args)
    args.goal, args.to, args.src, args.have = q, None, None, []
    return cmd_route(args)


def cmd_stats(args) -> int:
    with _read(args) as conn:
        s = queries.stats(conn)
    if args.json:
        print(json.dumps(s, indent=1))
    else:
        for r in s:
            print(f"  {r['label']:<12s} {r['n']}")
    return 0


def cmd_capture(args) -> int:
    from toolgraph.capture import capture, plan
    from toolgraph.discover import discover

    box = discover(Path(args.home).expanduser())
    out = Path(args.out).expanduser()
    steps = plan(box)
    if not args.yes:
        print("toolgraph capture starts each stdio MCP server in your config and calls tools/list.")
        print("It would run:")
        for name, cfg, status in steps:
            cmdline = " ".join([cfg.get("command", "")] + list(cfg.get("args") or []))
            print(f"  {name:20s} {status:28s} {cmdline}")
        print(f"Schemas would be written to {out}. Re-run with --yes to do it.")
        return 0
    capture(box, out, timeout=args.timeout)
    print(f"wrote schemas to {out}; now run: toolgraph ingest --home {args.home}")
    return 0


DEMO_QUESTIONS = [
    ("route", "I want to open a PR on my repo from a Jira ticket"),
    ("blast", "github"),
    ("audit", None),
    ("context", "fix the sentry error and open a pull request"),
]


def cmd_demo(args) -> int:
    """Ingest the fixture toolbox and answer the four questions."""
    args.fixtures, args.embed, args.json = True, None, False
    cmd_ingest(args)
    for kind, q in DEMO_QUESTIONS:
        title = {"route": f'ROUTE   "{q}"', "blast": f"BLAST RADIUS   remove the {q} server",
                 "audit": "AUDIT", "context": f'MINIMAL CONTEXT   "{q}"'}[kind]
        print("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100)
        if kind == "route":
            args.goal, args.to, args.src, args.have, args.project, args.mermaid = q, None, None, [], None, False
            cmd_route(args)
        elif kind == "blast":
            args.server, args.mermaid = q, False
            cmd_blast(args)
        elif kind == "audit":
            cmd_audit(args)
        else:
            args.goal, args.k, args.project = q, 8, None
            cmd_context(args)
    return 0


def cmd_serve(args) -> int:
    from toolgraph.mcp_server import serve
    serve(str(Path(args.database).resolve()))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="toolgraph", description="The connected map of your agent's toolbox.")
    p.add_argument("--version", action="version", version=f"toolgraph {__version__}")
    p.add_argument("--database", "-d", default=db.DEFAULT_DB, help="Relate store (default data/toolgraph.rl)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, mermaid=False, project=False):
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        if mermaid:
            sp.add_argument("--mermaid", action="store_true", help="Mermaid flowchart output")
        if project:
            sp.add_argument("--project", help="only servers enabled in this project (as keyed in ~/.claude.json)")
        return sp

    sp = common(sub.add_parser("ingest", help="build the graph from fixtures or your machine"))
    sp.add_argument("--fixtures", action="store_true", help="use the bundled fixture toolbox")
    sp.add_argument("--home", default="~", help="home directory to read agent config from (default ~)")
    sp.add_argument("--schemas", help=f"directory of tools/list JSON (default {CACHE_SCHEMAS})")
    sp.add_argument("--embed", choices=["hash", "fastembed"], help="also build a vector index for hybrid search")
    sp.set_defaults(fn=cmd_ingest)

    sp = common(sub.add_parser("ask", help="ask in plain English (routes to route/blast/audit/context)"), True, True)
    sp.add_argument("question")
    sp.add_argument("-k", type=int, default=8)
    sp.set_defaults(fn=cmd_ask)

    sp = common(sub.add_parser("route", help="which tools, in what order, for a goal"), True, True)
    sp.add_argument("goal", nargs="?")
    sp.add_argument("--to", help="entity to end with, e.g. pull_request")
    sp.add_argument("--from", dest="src", help="entity you start with, e.g. jira_issue")
    sp.add_argument("--have", action="append", default=[], help="entities you already have (repeatable)")
    sp.set_defaults(fn=cmd_route)

    sp = common(sub.add_parser("blast", help="what breaks if a server is removed"), True)
    sp.add_argument("server")
    sp.set_defaults(fn=cmd_blast)

    sp = common(sub.add_parser("audit", help="dangling references, dead hooks, collisions, duplicates"))
    sp.add_argument("--strict", action="store_true", help="exit 2 if anything is broken (for CI)")
    sp.set_defaults(fn=cmd_audit)

    sp = common(sub.add_parser("context", help="the k tools worth loading for a goal"), project=True)
    sp.add_argument("goal")
    sp.add_argument("-k", type=int, default=8)
    sp.set_defaults(fn=cmd_context)

    sp = common(sub.add_parser("stats", help="node counts"))
    sp.set_defaults(fn=cmd_stats)

    sp = sub.add_parser("capture", help="spawn your stdio MCP servers and save their tools/list")
    sp.add_argument("--home", default="~")
    sp.add_argument("--out", default=str(CACHE_SCHEMAS))
    sp.add_argument("--timeout", type=float, default=60.0)
    sp.add_argument("--yes", action="store_true", help="actually start the servers")
    sp.set_defaults(fn=cmd_capture)

    sp = sub.add_parser("demo", help="ingest the fixtures and answer the four questions")
    sp.set_defaults(fn=cmd_demo)

    sp = sub.add_parser("serve", help="run ToolGraph as an MCP server over stdio")
    sp.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except FileNotFoundError as e:
        print(f"toolgraph: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
