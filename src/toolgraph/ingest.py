"""Turn a discovered Toolbox into a Relate graph.

Few statements, not thousands: one ``UNWIND $batch`` per node/edge type inside a single
transaction (each autocommit is a WAL fsync). Every key is stable, so re-ingesting the same
toolbox produces the same graph.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from toolgraph import db
from toolgraph.builtin import BUILTIN_SERVER
from toolgraph.discover import MCP_REF, Toolbox, tool_id, trigger_phrases
from toolgraph.entities import GENERIC, consumes, produces

_WORD = re.compile(r"[a-z][a-z0-9]+")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "from", "by", "is", "this",
         "that", "returns", "return", "get", "list", "all", "new", "specific", "your", "its", "are", "be"}


def _tokens(s: str) -> set[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s).replace("_", " ").replace("-", " ").lower()
    return {w for w in _WORD.findall(s) if w not in _STOP}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _tool_tokens_cost(tool: dict) -> int:
    # ~4 characters per token for the JSON the agent would load into context
    return max(1, len(json.dumps(tool, separators=(",", ":"))) // 4)


def build_rows(box: Toolbox) -> dict[str, list]:
    rows: dict[str, list] = {k: [] for k in (
        "servers", "tools", "entities", "consumes", "produces", "skills", "requires", "triggers",
        "hooks", "matches", "plugins", "bundles", "projects", "enabled", "scoped", "instructions",
        "mentions", "overlaps")}
    known_tools: dict[str, dict] = {}
    entities: set[str] = set()

    for s in box.servers.values():
        rows["servers"].append({"id": s.id, "base": s.base, "scope": s.scope, "command": s.command,
                                "has_schema": s.has_schema, "plugin": s.plugin, "project": s.project,
                                "tool_count": len(s.tools),
                                "tokens": sum(_tool_tokens_cost(t) for t in s.tools)})
        for t in s.tools:
            tid = tool_id(s.id, t["name"])
            cons, prods = consumes(s.base, t), produces(t)
            known_tools[tid] = {"server": s.id, "cons": {c[0] for c in cons}, "prods": set(prods),
                                "tok": _tokens(t["name"]), "dtok": _tokens(t.get("description", ""))}
            rows["tools"].append({"id": tid, "name": t["name"], "server": s.id,
                                  "description": t.get("description", ""),
                                  "params": sorted((t.get("inputSchema") or {}).get("properties", {}).keys()),
                                  "tokens": _tool_tokens_cost(t), "missing": False})
            for ent, req, param in cons:
                entities.add(ent)
                rows["consumes"].append({"tool": tid, "entity": ent, "required": req, "param": param})
            for ent in prods:
                entities.add(ent)
                rows["produces"].append({"tool": tid, "entity": ent})

    ghost: dict[str, dict] = {}

    def resolve(ref: str) -> str:
        """Map a tool reference to a tool id, creating a ghost (not installed) tool if unknown."""
        if ref in known_tools:
            return ref
        m = MCP_REF.fullmatch(ref)
        if m is None and ref not in ghost:
            ghost[ref] = {"id": ref, "name": ref, "server": None, "description": "", "params": [],
                          "tokens": 0, "missing": True}
        elif m is not None and ref not in ghost:
            ghost[ref] = {"id": ref, "name": m.group(2), "server": m.group(1), "description": "",
                          "params": [], "tokens": 0, "missing": True}
        return ref

    builtin_names = {t for t, v in known_tools.items() if v["server"] == BUILTIN_SERVER}

    def tool_refs(text: str, extra: list[str] = ()) -> set[str]:
        refs = {m.group(0) for m in MCP_REF.finditer(text)}
        refs |= {b for b in builtin_names if f"`{b}`" in text}  # built-ins only when written as code
        refs |= {x for x in extra if x}
        return {resolve(r) for r in refs}

    for sk in box.skills:
        rows["skills"].append({"id": sk.id, "name": sk.name, "description": sk.description, "path": sk.path,
                               "scope": sk.scope, "plugin": sk.plugin, "project": sk.project,
                               "tokens": max(1, len(sk.description) // 4)})
        for ref in sorted(tool_refs(sk.body + "\n" + sk.description, sk.allowed_tools)):
            rows["requires"].append({"skill": sk.id, "tool": ref})
        for phrase in trigger_phrases(sk.description):
            rows["triggers"].append({"skill": sk.id, "keyword": phrase})
        if sk.plugin:
            rows["bundles"].append({"plugin": sk.plugin, "kind": "Skill", "id": sk.id})
        if sk.project:
            rows["scoped"].append({"kind": "Skill", "id": sk.id, "project": sk.project})

    all_tool_ids = sorted(known_tools)
    for h in box.hooks:
        rows["hooks"].append({"id": h.id, "event": h.event, "matcher": h.matcher, "command": h.command,
                              "source": h.source, "plugin": h.plugin})
        if h.matcher:
            try:
                rx = re.compile(h.matcher)
                for tid in all_tool_ids:
                    if rx.fullmatch(tid):
                        rows["matches"].append({"hook": h.id, "tool": tid})
            except re.error:
                pass
        if h.plugin:
            rows["bundles"].append({"plugin": h.plugin, "kind": "Hook", "id": h.id})

    for ins in box.instructions:
        rows["instructions"].append({"id": ins.id, "path": ins.path, "project": ins.project})
        for ref in sorted(tool_refs(ins.text)):
            rows["mentions"].append({"instruction": ins.id, "tool": ref})
        if ins.project:
            rows["scoped"].append({"kind": "Instruction", "id": ins.id, "project": ins.project})

    for p in box.plugins.values():
        rows["plugins"].append(p)
    for s in box.servers.values():
        if s.plugin:
            rows["bundles"].append({"plugin": s.plugin, "kind": "Server", "id": s.id})

    # Enablement: user + plugin servers are on everywhere unless a project disables them;
    # project servers only in their project.
    for key, p in box.projects.items():
        rows["projects"].append({"path": key})
        for s in box.servers.values():
            if s.scope == "project" and s.project != key:
                continue
            if s.base in p["disabled"] or s.id in p["disabled"]:
                continue
            rows["enabled"].append({"server": s.id, "project": key})

    rows["tools"] += sorted(ghost.values(), key=lambda g: g["id"])
    rows["entities"] = [{"name": e, "generic": e in GENERIC} for e in sorted(entities)]

    # OVERLAPS_WITH: tools on different servers that move the same entities and read alike.
    ids = all_tool_ids
    for i, a in enumerate(ids):
        ta = known_tools[a]
        for b in ids[i + 1:]:
            tb = known_tools[b]
            if ta["server"] == tb["server"]:
                continue
            ea = ta["cons"] - GENERIC | ta["prods"] - GENERIC
            eb = tb["cons"] - GENERIC | tb["prods"] - GENERIC
            ent_sim = _jaccard(ea, eb)
            if ent_sim < 0.3:
                continue
            name_sim = _jaccard(ta["tok"], tb["tok"])
            desc_sim = _jaccard(ta["dtok"] | ta["tok"], tb["dtok"] | tb["tok"])
            score = round(0.4 * ent_sim + 0.35 * name_sim + 0.25 * desc_sim, 3)
            if score >= 0.4 and (name_sim >= 0.3 or desc_sim >= 0.3):
                rows["overlaps"].append({"a": a, "b": b, "score": score,
                                         "shared": sorted(ea & eb)})
    return rows


STATEMENTS: list[tuple[str, str]] = [
    ("agent", "MERGE (a:Agent {name: $agent}) SET a.home = $home"),
    ("servers", """UNWIND $batch AS r MERGE (s:Server {id: r.id})
        SET s.name = r.id, s.base = r.base, s.scope = r.scope, s.command = r.command,
            s.has_schema = r.has_schema, s.tool_count = r.tool_count, s.tokens = r.tokens, s.missing = false
        WITH s MATCH (a:Agent {name: $agent}) MERGE (a)-[:USES]->(s)"""),
    ("entities", "UNWIND $batch AS r MERGE (e:Entity {name: r.name}) SET e.generic = r.generic"),
    ("tools", """UNWIND $batch AS r MERGE (t:Tool {id: r.id})
        SET t.name = r.name, t.server = r.server, t.description = r.description, t.params = r.params,
            t.tokens = r.tokens, t.missing = r.missing"""),
    ("tools", """UNWIND $batch AS r WITH r WHERE NOT r.missing
        MATCH (s:Server {id: r.server}), (t:Tool {id: r.id}) MERGE (s)-[:PROVIDES]->(t)"""),
    ("consumes", """UNWIND $batch AS r MATCH (t:Tool {id: r.tool}), (e:Entity {name: r.entity})
        MERGE (t)-[c:CONSUMES]->(e) SET c.required = r.required, c.param = r.param"""),
    ("produces", """UNWIND $batch AS r MATCH (t:Tool {id: r.tool}), (e:Entity {name: r.entity})
        MERGE (t)-[:PRODUCES]->(e)"""),
    ("plugins", """UNWIND $batch AS r MERGE (p:Plugin {name: r.name})
        SET p.version = r.version, p.description = r.description, p.path = r.path
        WITH p MATCH (a:Agent {name: $agent}) MERGE (a)-[:INSTALLED]->(p)"""),
    ("skills", """UNWIND $batch AS r MERGE (k:Skill {id: r.id})
        SET k.name = r.name, k.description = r.description, k.path = r.path, k.scope = r.scope, k.tokens = r.tokens
        WITH k MATCH (a:Agent {name: $agent}) MERGE (a)-[:HAS_SKILL]->(k)"""),
    ("requires", """UNWIND $batch AS r MATCH (k:Skill {id: r.skill}), (t:Tool {id: r.tool})
        MERGE (k)-[:REQUIRES_TOOL]->(t)"""),
    ("triggers", """UNWIND $batch AS r MATCH (k:Skill {id: r.skill}) MERGE (w:Keyword {text: r.keyword})
        MERGE (k)-[:TRIGGERS_ON]->(w)"""),
    ("hooks", """UNWIND $batch AS r MERGE (h:Hook {id: r.id})
        SET h.event = r.event, h.matcher = r.matcher, h.command = r.command, h.source = r.source
        WITH h MATCH (a:Agent {name: $agent}) MERGE (a)-[:HAS_HOOK]->(h)"""),
    ("matches", """UNWIND $batch AS r MATCH (h:Hook {id: r.hook}), (t:Tool {id: r.tool}) MERGE (h)-[:MATCHES]->(t)"""),
    ("instructions", """UNWIND $batch AS r MERGE (i:Instruction {id: r.id}) SET i.path = r.path"""),
    ("mentions", """UNWIND $batch AS r MATCH (i:Instruction {id: r.instruction}), (t:Tool {id: r.tool})
        MERGE (i)-[:MENTIONS]->(t)"""),
    ("projects", "UNWIND $batch AS r MERGE (p:Project {path: r.path})"),
    ("enabled", """UNWIND $batch AS r MATCH (s:Server {id: r.server}), (p:Project {path: r.project})
        MERGE (s)-[:ENABLED_IN]->(p)"""),
    ("scoped", """UNWIND $batch AS r MATCH (p:Project {path: r.project}), (n {id: r.id})
        WHERE r.kind IN labels(n) MERGE (n)-[:SCOPED_TO]->(p)"""),
    ("bundles", """UNWIND $batch AS r MATCH (p:Plugin {name: r.plugin}), (n {id: r.id})
        WHERE r.kind IN labels(n) MERGE (p)-[:BUNDLES]->(n)"""),
    ("overlaps", """UNWIND $batch AS r MATCH (a:Tool {id: r.a}), (b:Tool {id: r.b})
        MERGE (a)-[o:OVERLAPS_WITH]->(b) SET o.score = r.score, o.shared = r.shared"""),
]

INDEXES = [
    "CREATE FULLTEXT INDEX tool_text IF NOT EXISTS FOR (t:Tool) ON EACH [t.name, t.description]",
    "CREATE FULLTEXT INDEX skill_text IF NOT EXISTS FOR (k:Skill) ON EACH [k.name, k.description]",
]


def ingest_into(box: Toolbox, conn) -> dict[str, int]:
    """Load the toolbox into an open connection in one transaction. Returns row counts."""
    rows = build_rows(box)
    base = {"agent": box.agent, "home": box.home}
    conn.autocommit = False
    for key, stmt in STATEMENTS:
        if key == "agent":
            conn.execute(stmt, base)
        elif rows[key]:
            conn.execute(stmt, {**base, "batch": rows[key]})
    conn.commit()
    conn.autocommit = True
    for stmt in INDEXES:
        conn.execute(stmt)
    return {k: len(v) for k, v in rows.items()}


def ingest(box: Toolbox, path: str | Path) -> dict[str, int]:
    """Rebuild the store at ``path`` from scratch (deterministic; one writer)."""
    db.remove_store(path)
    with db.open_store(path) as conn:
        return ingest_into(box, conn)
