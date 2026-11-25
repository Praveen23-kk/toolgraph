"""Human-readable and Mermaid renderings of answers (JSON is just ``json.dumps``)."""
from __future__ import annotations

import re

_TOOL_REF = re.compile(r"mcp__[\w.-]+?__[\w.-]+")


def short(tool_id: str) -> str:
    """mcp__github__create_branch -> github.create_branch (built-ins stay as they are)."""
    if tool_id.startswith("mcp__"):
        server, _, name = tool_id[5:].partition("__")
        return f"{server.replace('plugin_', '')}.{name}"
    return tool_id


def why(text: str) -> str:
    return _TOOL_REF.sub(lambda m: short(m.group(0)), text)


def _mid(s: str) -> str:
    return "n_" + "".join(c if c.isalnum() else "_" for c in s)


# ------------------------------------------------------------------- text
def route_text(r: dict) -> str:
    if "error" in r:
        return "route: " + r["error"]
    out = [f"goal: {r['goal']}" if r.get("goal") else "",
           f"from {r['from'] or '(nothing)'} -> to {r['to']}" + (f"   (you have: {', '.join(r['have'])})" if r["have"] else "")]
    if not r["steps"]:
        out.append("no tool chain found")
    for i, s in enumerate(r["steps"], 1):
        out.append(f"  {i}. {short(s['tool']):48s} {why(s['why'])}")
    if r["you_supply"]:
        out.append("you supply: " + ", ".join(f"{k} ({v.split(' for ')[0]})" for k, v in r["you_supply"].items()))
    if r["steps"] and not r["reachable"]:
        out.append("warning: the chain does not end in " + r["to"])
    return "\n".join(x for x in out if x)


def blast_text(b: dict) -> str:
    if "error" in b:
        return "blast radius: " + b["error"]
    out = [f"remove server '{b['server']}' ({b['scope']}): {len(b['lost_tools'])} tools, ~{b['tokens']} tokens of context",
           f"  enabled in projects: {', '.join(b['projects']) or '-'}"
           + (f"; shipped by plugin {', '.join(b['plugins'])}" if b["plugins"] else "")]
    for label in ("broken", "degraded"):
        for d in b[label]:
            lost = ", ".join(short(t) for t in d["lost"])
            out.append(f"  {label.upper():9s} {d['kind']:<11s} {d['name']:<34s} loses {d['lost_count']}/{d['total']}: {lost}")
    if not b["broken"] and not b["degraded"]:
        out.append("  nothing references this server's tools")
    for o in b["orphaned_entities"]:
        stranded = ", ".join(short(t) for t in o["stranded"]) or "-"
        out.append(f"  ORPHANED  entity {o['entity']:<20s} nothing else produces it; stranded: {stranded}")
    return "\n".join(out)


def audit_text(a: dict) -> str:
    out = []
    out.append(f"[dangling] {len(a['dangling'])} reference(s) to tools that are not installed")
    for d in a["dangling"]:
        out.append(f"  {d['kind']:<11s} {d['name']:<22s} -> {d['tool']}  (server '{d['missing_server']}' not configured)")
    out.append(f"[dead hooks] {len(a['dead_hooks'])} hook(s) whose matcher matches no tool")
    for h in a["dead_hooks"]:
        out.append(f"  {h['event']:<12s} matcher {h['matcher']!r} -> {h['command']}")
    out.append(f"[collisions] {len(a['collisions'])} skill pair(s) triggered by the same phrase")
    for c in a["collisions"]:
        dup = "  (same skill installed twice)" if c.get("same_name") else ""
        out.append(f"  {c['skill_a']} <-> {c['skill_b']}: {'; '.join(c['phrases'])}{dup}")
    out.append(f"[overlaps] {len(a['overlaps'])} tool pair(s) on different servers doing the same job")
    for o in a["overlaps"]:
        out.append(f"  {short(o['tool_a']):<36s} ~ {short(o['tool_b']):<40s} score {o['score']:.2f} via {', '.join(o['shared'])}")
    out.append(f"[unused] {len(a['unused'])} server(s) no skill, hook or CLAUDE.md uses")
    for u in a["unused"]:
        out.append(f"  {u['server']:<20s} {u['tools']} tools, ~{u['tokens']} tokens loaded for nothing")
    if a["no_schema"]:
        out.append(f"[no schema] {len(a['no_schema'])} server(s) without a captured tool list (run `toolgraph capture`)")
        for s in a["no_schema"]:
            out.append(f"  {s['server']:<20s} {s['command']}")
    return "\n".join(out)


def context_text(c: dict) -> str:
    out = [f"goal: {c['goal']}",
           f"load {len(c['tools'])} of {c['tools_total']} tools: ~{c['tokens_loaded']} of ~{c['tokens_all_tools']} tokens "
           f"({c['saved_pct']}% less context)"]
    for t in c["tools"]:
        out.append(f"  {short(t['tool']):48s} {t['tokens']:>5} tok  {why(t['reason'])}")
    return "\n".join(out)


# ---------------------------------------------------------------- mermaid
def route_mermaid(r: dict) -> str:
    lines = ["flowchart LR"]
    prev = None
    if r.get("from"):
        prev = _mid("e_" + r["from"])
        lines.append(f'  {prev}(["{r["from"]}"])')
    for s in r.get("steps", []):
        n = _mid(s["tool"])
        lines.append(f'  {n}["{short(s["tool"])}"]')
        if prev:
            lines.append(f"  {prev} --> {n}")
        prev = n
    if r.get("to") and prev:
        lines.append(f'  {_mid("e_" + r["to"])}(["{r["to"]}"])')
        lines.append(f'  {prev} --> {_mid("e_" + r["to"])}')
    return "\n".join(lines)


def blast_mermaid(b: dict) -> str:
    if "error" in b:
        return f"%% {b['error']}"
    s = _mid("s_" + b["server"])
    lines = ["flowchart LR", f'  {s}[("{b["server"]}")]:::server']
    for label in ("broken", "degraded"):
        for d in b[label]:
            n = _mid(d["id"])
            lines.append(f'  {n}["{d["kind"]}: {d["name"]}"]:::{label}')
            lines.append(f'  {s} -- "{d["lost_count"]}/{d["total"]} tools" --> {n}')
    for o in b["orphaned_entities"]:
        e = _mid("e_" + o["entity"])
        lines.append(f'  {e}(["{o["entity"]}"]):::orphan')
        lines.append(f"  {s} -. only producer .-> {e}")
    lines += ["  classDef server fill:#ffd9b3,stroke:#c60", "  classDef broken fill:#f8b4b4,stroke:#b00",
              "  classDef degraded fill:#fde68a,stroke:#a60", "  classDef orphan fill:#e5e7eb,stroke:#666"]
    return "\n".join(lines)
