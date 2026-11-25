"""Capture real tool schemas by spawning each configured stdio MCP server and calling tools/list.

This runs the commands in your agent config (the same ones Claude Code would run), so it is
opt-in: ``toolgraph capture`` lists what it would start and needs ``--yes`` to do it.
Remote (http/sse) servers are skipped; they usually need OAuth.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

from toolgraph.discover import Toolbox, _read_json


def _configs(home: Path) -> dict[str, dict]:
    """base server name -> launch config, from ~/.claude.json, projects, .mcp.json and plugins."""
    out: dict[str, dict] = {}
    cj = _read_json(home / ".claude.json")
    out.update(cj.get("mcpServers") or {})
    for key, p in (cj.get("projects") or {}).items():
        out.update(p.get("mcpServers") or {})
        ppath = home / key[1:].lstrip("/\\") if key.startswith("~") else Path(key)
        out.update(_read_json(ppath / ".mcp.json").get("mcpServers") or {})
    plugins = home / ".claude" / "plugins"
    for manifest in plugins.rglob(".claude-plugin/plugin.json") if plugins.is_dir() else []:
        meta = _read_json(manifest)
        if isinstance(meta.get("mcpServers"), dict):
            out.update(meta["mcpServers"])
        out.update(_read_json(manifest.parent.parent / ".mcp.json").get("mcpServers") or {})
    return out


def plan(box: Toolbox) -> list[tuple[str, dict, str]]:
    """[(name, config, status)] where status is 'spawn' or a reason to skip."""
    res = []
    for name, cfg in sorted(_configs(Path(box.home)).items()):
        if cfg.get("type") in ("http", "sse") or "url" in cfg:
            res.append((name, cfg, "skip: remote server"))
        elif not cfg.get("command"):
            res.append((name, cfg, "skip: no command"))
        elif shutil.which(cfg["command"]) is None:
            res.append((name, cfg, f"skip: {cfg['command']} not on PATH"))
        else:
            res.append((name, cfg, "spawn"))
    return res


async def _next_page(session, cursor: str):
    try:  # mcp >= 2
        from mcp import types
        return await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor))
    except TypeError:  # mcp 1.x
        return await session.list_tools(cursor)


async def _list_tools(cfg: dict, timeout: float) -> list[dict]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}}
    params = StdioServerParameters(command=shutil.which(cfg["command"]) or cfg["command"],
                                   args=list(cfg.get("args") or []), env=env)

    async def go():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools, cursor = [], None
                while True:
                    page = await (_next_page(s, cursor) if cursor else s.list_tools())
                    tools += [t.model_dump(exclude_none=True, by_alias=True) for t in page.tools]
                    cursor = getattr(page, "next_cursor", None) or getattr(page, "nextCursor", None)
                    if not cursor:
                        return tools
    return await asyncio.wait_for(go(), timeout)


def capture(box: Toolbox, out_dir: Path, timeout: float = 60.0, log=print) -> dict[str, int | str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, int | str] = {}
    for name, cfg, status in plan(box):
        if status != "spawn":
            results[name] = status
            log(f"  {name:20s} {status}")
            continue
        try:
            tools = asyncio.run(_list_tools(cfg, timeout))
        except Exception as e:  # a broken server should not stop the rest
            results[name] = f"error: {type(e).__name__}: {e}"[:200]
            log(f"  {name:20s} {results[name]}")
            continue
        doc = {"server": name, "transport": "stdio", "command": cfg["command"], "args": cfg.get("args", []),
               "source": "captured with toolgraph capture (tools/list)", "tools": tools}
        (out_dir / f"{name}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
        results[name] = len(tools)
        log(f"  {name:20s} {len(tools)} tools")
    return results
