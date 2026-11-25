"""Discover an agent's toolbox on disk: MCP servers, skills, plugins, hooks, CLAUDE.md, projects.

Works the same on the fixture home (``fixtures/home``) and on a real ``~``. Nothing here
spawns a process or touches the network; tool schemas come from a schema directory
(``fixtures/servers`` or the cache written by ``toolgraph capture``).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from toolgraph.builtin import BUILTIN_SERVER, BUILTIN_TOOLS

MCP_REF = re.compile(r"mcp__([A-Za-z0-9_.-]+?)__([A-Za-z0-9_.-]+)")
QUOTED = re.compile(r'["“]([^"”]{2,40})["”]')


@dataclass
class ServerDef:
    id: str                      # the name Claude Code prefixes tool ids with (mcp__<id>__tool)
    base: str                    # the server name used to find its schema file
    scope: str                   # user | project | plugin
    command: str = ""
    project: str | None = None
    plugin: str | None = None
    tools: list[dict] = field(default_factory=list)
    has_schema: bool = False


@dataclass
class SkillDef:
    id: str
    name: str
    description: str
    body: str
    path: str
    scope: str
    allowed_tools: list[str]
    project: str | None = None
    plugin: str | None = None


@dataclass
class HookDef:
    id: str
    event: str
    matcher: str | None
    command: str
    source: str
    plugin: str | None = None


@dataclass
class InstructionDef:
    id: str
    path: str
    text: str
    project: str | None = None


@dataclass
class Toolbox:
    agent: str
    home: str
    servers: dict[str, ServerDef] = field(default_factory=dict)
    skills: list[SkillDef] = field(default_factory=list)
    hooks: list[HookDef] = field(default_factory=list)
    instructions: list[InstructionDef] = field(default_factory=list)
    plugins: dict[str, dict] = field(default_factory=dict)
    projects: dict[str, dict] = field(default_factory=dict)   # path -> {"disabled": [...]}


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _frontmatter(text: str) -> tuple[dict, str]:
    """Tiny YAML-frontmatter reader: flat ``key: value`` pairs only (enough for SKILL.md)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, text[end + 4:].lstrip("\n")


def _resolve_project(home: Path, key: str) -> Path:
    if key.startswith("~"):
        return home / key[1:].lstrip("/\\")
    return Path(key)


def _plugin_server_id(plugin: str, server: str) -> str:
    # Claude Code exposes plugin servers as mcp__plugin_<plugin>_<server>__<tool>
    return f"plugin_{plugin}_{server}"


def load_schemas(schema_dir: Path | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if schema_dir and schema_dir.is_dir():
        for f in sorted(schema_dir.glob("*.json")):
            doc = _read_json(f)
            if doc.get("tools") is not None:
                out[doc.get("server", f.stem)] = doc
    return out


def _read_skill(path: Path, scope: str, project: str | None = None, plugin: str | None = None) -> SkillDef:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _frontmatter(text)
    name = meta.get("name") or path.parent.name
    allowed = [t.strip() for t in re.split(r"[,\s]+", meta.get("allowed-tools", "")) if t.strip()]
    sid = f"{plugin + ':' if plugin else ''}{project + ':' if project else ''}{name}"
    return SkillDef(id=sid, name=name, description=meta.get("description", ""), body=body,
                    path=str(path), scope=scope, allowed_tools=allowed, project=project, plugin=plugin)


def _read_hooks(settings: dict, source: str, plugin: str | None = None) -> list[HookDef]:
    hooks = []
    for event, groups in (settings.get("hooks") or {}).items():
        for gi, group in enumerate(groups or []):
            for hi, h in enumerate(group.get("hooks") or []):
                hooks.append(HookDef(id=f"{source}#{event}[{gi}.{hi}]", event=event,
                                     matcher=group.get("matcher") or None,
                                     command=h.get("command", h.get("url", "")), source=source, plugin=plugin))
    return hooks


def _add_server(box: Toolbox, schemas: dict, sid: str, base: str, cfg: dict, scope: str,
                project: str | None = None, plugin: str | None = None) -> None:
    if sid in box.servers:
        return
    schema = schemas.get(base) or schemas.get(sid)
    cmd = " ".join([cfg.get("command", "")] + list(cfg.get("args", []))).strip() or cfg.get("url", "")
    box.servers[sid] = ServerDef(id=sid, base=base, scope=scope, command=cmd, project=project, plugin=plugin,
                                 tools=list(schema["tools"]) if schema else [], has_schema=bool(schema))


def discover(home: Path, schema_dir: Path | None = None, agent: str = "claude-code") -> Toolbox:
    home = Path(home).expanduser()
    schemas = load_schemas(schema_dir)
    box = Toolbox(agent=agent, home=str(home))
    box.servers[BUILTIN_SERVER] = ServerDef(id=BUILTIN_SERVER, base=BUILTIN_SERVER, scope="builtin",
                                            command="(built into the agent)", tools=BUILTIN_TOOLS, has_schema=True)

    cj = _read_json(home / ".claude.json")
    for name, cfg in (cj.get("mcpServers") or {}).items():
        _add_server(box, schemas, name, name, cfg, "user")

    claude_dir = home / ".claude"
    settings = _read_json(claude_dir / "settings.json")
    box.hooks += _read_hooks(settings, "user-settings")
    if (claude_dir / "CLAUDE.md").is_file():
        box.instructions.append(InstructionDef(id="user:CLAUDE.md", path=str(claude_dir / "CLAUDE.md"),
                                               text=(claude_dir / "CLAUDE.md").read_text(encoding="utf-8")))
    for sk in sorted((claude_dir / "skills").glob("*/SKILL.md")):
        box.skills.append(_read_skill(sk, "user"))

    # Plugins: any .claude-plugin/plugin.json below ~/.claude/plugins (covers the marketplace cache layout).
    plugin_root = claude_dir / "plugins"
    seen_plugins: set[str] = set()
    for manifest in sorted(plugin_root.rglob(".claude-plugin/plugin.json")) if plugin_root.is_dir() else []:
        pdir = manifest.parent.parent
        meta = _read_json(manifest)
        pname = meta.get("name") or pdir.name
        if pname in seen_plugins:
            continue
        seen_plugins.add(pname)
        box.plugins[pname] = {"name": pname, "version": meta.get("version", ""),
                              "description": meta.get("description", ""), "path": str(pdir)}
        servers = dict(meta.get("mcpServers") or {}) if isinstance(meta.get("mcpServers"), dict) else {}
        servers.update(_read_json(pdir / ".mcp.json").get("mcpServers") or {})
        for name, cfg in servers.items():
            _add_server(box, schemas, _plugin_server_id(pname, name), name, cfg, "plugin", plugin=pname)
        for sk in sorted((pdir / "skills").glob("*/SKILL.md")):
            box.skills.append(_read_skill(sk, "plugin", plugin=pname))
        hooks_file = pdir / "hooks" / "hooks.json"
        if hooks_file.is_file():
            box.hooks += _read_hooks(_read_json(hooks_file), f"plugin:{pname}", plugin=pname)

    # Projects: from ~/.claude.json, each with its own servers, .mcp.json, skills and CLAUDE.md.
    for key, pcfg in (cj.get("projects") or {}).items():
        ppath = _resolve_project(home, key)
        box.projects[key] = {"path": key, "disabled": list(pcfg.get("disabledMcpServers") or [])
                             + list(pcfg.get("disabledMcpjsonServers") or [])}
        for name, cfg in (pcfg.get("mcpServers") or {}).items():
            _add_server(box, schemas, name, name, cfg, "project", project=key)
        for name, cfg in (_read_json(ppath / ".mcp.json").get("mcpServers") or {}).items():
            _add_server(box, schemas, name, name, cfg, "project", project=key)
        for sk in sorted((ppath / ".claude" / "skills").glob("*/SKILL.md")):
            box.skills.append(_read_skill(sk, "project", project=key))
        box.hooks += _read_hooks(_read_json(ppath / ".claude" / "settings.json"), f"project:{key}")
        for md in (ppath / "CLAUDE.md", ppath / ".claude" / "CLAUDE.md"):
            if md.is_file():
                box.instructions.append(InstructionDef(id=f"{key}:CLAUDE.md", path=str(md),
                                                       text=md.read_text(encoding="utf-8"), project=key))
    return box


def tool_id(server_id: str, tool_name: str) -> str:
    return tool_name if server_id == BUILTIN_SERVER else f"mcp__{server_id}__{tool_name}"


def trigger_phrases(description: str) -> list[str]:
    """Phrases a skill is meant to fire on: quoted phrases in its description, lower-cased."""
    return sorted({m.strip().lower() for m in QUOTED.findall(description) if m.strip()})
