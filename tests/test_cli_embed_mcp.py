import asyncio
import json
import sys

import pytest

from toolgraph import db
from toolgraph.cli import main
from toolgraph.discover import discover
from toolgraph.embed import add_vectors, hash_embedder, hybrid_search
from toolgraph.ingest import ingest

from conftest import HOME, SCHEMAS


def test_cli_end_to_end(tmp_path, capsys):
    store = str(tmp_path / "g.rl")
    assert main(["-d", store, "ingest", "--fixtures"]) == 0
    capsys.readouterr()
    assert main(["-d", store, "route", "--json", "open a PR on my repo from a Jira ticket"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["steps"][-1]["tool"] == "mcp__github__create_pull_request"
    assert main(["-d", store, "ask", "what breaks if I remove the slack server"]) == 0
    assert "remove server 'slack'" in capsys.readouterr().out
    assert main(["-d", store, "audit", "--strict"]) == 2
    capsys.readouterr()
    assert main(["-d", store, "blast", "--mermaid", "github"]) == 0
    assert capsys.readouterr().out.startswith("flowchart LR")


def test_missing_store_is_a_clean_error(tmp_path):
    assert main(["-d", str(tmp_path / "none.rl"), "audit"]) == 3


def test_hybrid_vector_search(tmp_path):
    store = tmp_path / "v.rl"
    ingest(discover(HOME, SCHEMAS), store)
    emb = hash_embedder()
    with db.open_store(store) as conn:
        assert add_vectors(conn, emb) == 107
        hits = hybrid_search(conn, "post a message to a slack channel", emb, limit=5)
    assert hits[0]["id"] == "mcp__slack__slack_post_message"


def test_mcp_server_stdio_roundtrip(store):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "toolgraph.cli", "-d", str(store), "serve"])
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                res = await s.call_tool("blast_radius", {"server": "github"})
                return names, json.loads(res.content[0].text)

    names, blast = asyncio.run(asyncio.wait_for(go(), 60))
    assert {"route_tools", "blast_radius", "audit_toolbox", "find_tools", "read_cypher"} <= names
    assert len(blast["lost_tools"]) == 23 and blast["mermaid"].startswith("flowchart")
