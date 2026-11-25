"""The four questions: route, blast radius, audit, minimal context.

Each answer is a plain dict (JSON-serialisable) built from the named Cypher files in
``toolgraph/cypher``. Path finding and dependency traversal happen in the graph; Python only
orders steps and stitches results together.
"""
from __future__ import annotations

import re

from toolgraph.db import cypher, rows
from toolgraph.entities import parse_goal

_FT_SPECIAL = re.compile(r"[^a-z0-9\s]")
_FT_STOP = {"i", "want", "to", "a", "an", "the", "my", "me", "for", "from", "on", "in", "of", "and", "with",
            "need", "how", "do", "can", "you", "it", "this", "that", "into", "give", "which", "what", "tools",
            "tool", "please", "our", "is", "be", "then"}


def servers_for(conn, project: str | None) -> list[str] | None:
    if not project:
        return None
    return rows(conn, cypher("project_servers"), {"project": project})[0]["servers"]


# --------------------------------------------------------------------------- route
def route(conn, to: str | None = None, src: str | None = None, have: list[str] | None = None,
          goal: str | None = None, project: str | None = None, max_depth: int = 2) -> dict:
    """Order the tools that get from ``src`` (and anything in ``have``) to ``to``."""
    if goal:
        parsed = parse_goal(goal)
        to = to or parsed["to"]
        src = src or parsed["from"]
        have = list(dict.fromkeys((have or []) + parsed["have"]))
    have = [h for h in (have or []) if h]
    if not to:
        return {"error": "could not tell what you want to end up with; pass --to <entity>", "goal": goal}
    servers = servers_for(conn, project)
    available = set(have) | ({src} if src else set())
    chain_tools: list[str] = []
    chain: list[str] = []
    if src and src != to:
        found = rows(conn, cypher("route_path"), {"from": src, "to": to, "servers": servers})
        if found:
            chain_tools, chain = found[0]["tools"], found[0]["chain"]

    steps: list[dict] = []
    supply: dict[str, str] = {}
    placed: set[str] = set()

    def produced_by(tid: str) -> list[str]:
        return rows(conn, cypher("tool_produces"), {"id": tid})[0]["entities"]

    def tool_server(tid: str) -> str | None:
        found = rows(conn, "MATCH (t:Tool {id: $id}) RETURN t.server AS s", {"id": tid})
        return found[0]["s"] if found else None

    def place(tid: str, why: str, depth: int) -> None:
        if tid in placed:
            return
        placed.add(tid)  # mark early so cycles stop here
        for need in rows(conn, cypher("tool_needs"), {"id": tid}):
            ent = need["entity"]
            if need["self"] or ent in available:
                continue
            if need["generic"]:
                supply.setdefault(ent, f"{need['param']} for {tid}")
                continue
            prods = [] if depth >= max_depth else rows(conn, cypher("producers"), {
                "entity": ent, "have": sorted(available), "servers": servers, "exclude": sorted(placed),
                "prefer": tool_server(tid)})
            if prods:
                place(prods[0]["id"], f"produces {ent} for {tid}", depth + 1)
            else:
                supply.setdefault(ent, f"{need['param']} for {tid}")
        steps.append({"tool": tid, "why": why})
        available.update(produced_by(tid))

    if chain_tools:
        for i, tid in enumerate(chain_tools):
            nxt = chain[2 * i + 2] if 2 * i + 2 < len(chain) else to
            place(tid, f"turns {chain[2 * i]} into {nxt}", 0)
    elif to not in available:
        prods = rows(conn, cypher("producers"), {"entity": to, "have": sorted(available),
                                                 "servers": servers, "exclude": [], "prefer": None})
        if prods:
            place(prods[0]["id"], f"produces {to}", 0)

    return {"goal": goal, "from": src, "to": to, "have": have, "project": project,
            "path": chain, "steps": steps, "you_supply": supply,
            "reachable": any(to in produced_by(s["tool"]) for s in steps)}


# ----------------------------------------------------------------- blast radius
def blast_radius(conn, server: str) -> dict:
    meta = rows(conn, cypher("blast_projects"), {"server": server})
    if not meta or meta[0]["scope"] is None:
        return {"error": f"no server named {server!r}", "server": server}
    deps = rows(conn, cypher("blast_dependents"), {"server": server})
    # broken: loses every tool, or at least half of what it uses; degraded: loses a fallback.
    for d in deps:
        d["status"] = "broken" if d["dead"] or 2 * d["lost_count"] >= d["total"] else "degraded"
    return {
        "server": server, **meta[0],
        "lost_tools": [r["tool"] for r in rows(conn, cypher("blast_tools"), {"server": server})],
        "broken": [d for d in deps if d["status"] == "broken"],
        "degraded": [d for d in deps if d["status"] == "degraded"],
        "orphaned_entities": rows(conn, cypher("blast_orphans"), {"server": server}),
    }


# ------------------------------------------------------------------------ audit
def audit(conn) -> dict:
    return {name: rows(conn, cypher(f"audit_{name}")) for name in
            ("dangling", "dead_hooks", "collisions", "overlaps", "unused", "no_schema")}


# --------------------------------------------------------------- minimal context
def _ft_query(goal: str) -> str:
    words = [w for w in _FT_SPECIAL.sub(" ", goal.lower()).split() if w not in _FT_STOP and len(w) > 1]
    return " OR ".join(dict.fromkeys(words)) or "*"


def minimal_context(conn, goal: str, k: int = 8, project: str | None = None, embed=None) -> dict:
    """The k tools worth loading for a goal: route tools, then skill tools, then search hits,
    then graph neighbours. ``embed`` (optional) is a callable text -> vector for hybrid search."""
    servers = servers_for(conn, project)
    picked: dict[str, str] = {}

    def add(tid: str, reason: str) -> None:
        if len(picked) < k and tid not in picked:
            picked[tid] = reason

    r = route(conn, goal=goal, project=project)
    for s in r.get("steps", []):
        add(s["tool"], "route: " + s["why"])
    q = _ft_query(goal)
    skills = rows(conn, cypher("context_skills"), {"q": q})
    for sk in skills[:1]:
        for tid in sk["tools"]:
            if servers is None or any(tid == x or tid.startswith(f"mcp__{x}__") for x in servers):
                add(tid, f"skill {sk['skill']}")
    if embed is not None:
        from toolgraph.embed import hybrid_search
        for hit in hybrid_search(conn, goal, embed, limit=20):
            if servers is None or hit["server"] in servers:
                add(hit["id"], f"hybrid search (rrf {hit['rrf']:.3f})")
    else:
        for hit in rows(conn, cypher("context_search"), {"q": q, "servers": servers})[:10]:
            add(hit["id"], f"full-text match ({hit['score']:.2f})")
    if len(picked) < k and picked:
        for n in rows(conn, cypher("context_neighbours"), {"seeds": list(picked), "servers": servers}):
            add(n["id"], f"shares {n['links']} entity link(s) with the picks")

    tot = rows(conn, cypher("totals"), {"servers": servers})[0]
    tok = {t["id"]: t["tokens"] for t in rows(conn, "MATCH (t:Tool) WHERE t.id IN $ids RETURN t.id AS id, t.tokens AS tokens",
                                                {"ids": list(picked)})}
    used = sum(tok.get(t, 0) or 0 for t in picked)
    return {"goal": goal, "project": project, "k": k,
            "tools": [{"tool": t, "reason": why, "tokens": tok.get(t, 0)} for t, why in picked.items()],
            "tokens_loaded": used, "tokens_all_tools": tot["tokens"], "tools_total": tot["tools"],
            "saved_pct": round(100 * (1 - used / tot["tokens"]), 1) if tot["tokens"] else 0.0}


def stats(conn) -> list[dict]:
    return rows(conn, cypher("stats"))
