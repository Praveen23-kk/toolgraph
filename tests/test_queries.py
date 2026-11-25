from toolgraph import queries
from toolgraph.db import rows
from toolgraph.ingest import build_rows


def test_ingest_is_deterministic(box):
    assert build_rows(box) == build_rows(box)


def test_graph_shape(conn):
    counts = {r["label"]: r["n"] for r in queries.stats(conn)}
    assert counts["Server"] == 13 and counts["Skill"] == 11 and counts["Plugin"] == 2
    # ghost tools exist for the three uninstalled servers, with no PROVIDES edge
    ghosts = rows(conn, "MATCH (t:Tool) WHERE NOT EXISTS { (:Server)-[:PROVIDES]->(t) } RETURN t.id AS id ORDER BY id")
    assert [g["id"] for g in ghosts] == ["mcp__linear__update_issue", "mcp__notion__create_page",
                                         "mcp__pagerduty__create_incident"]


def test_route_jira_to_pr(conn):
    r = queries.route(conn, goal="I want to open a PR on my repo from a Jira ticket")
    assert [s["tool"] for s in r["steps"]] == [
        "mcp__plugin_jira-flow_atlassian__getAccessibleAtlassianResources",
        "mcp__plugin_jira-flow_atlassian__getJiraIssue",
        "mcp__github__create_branch",
        "mcp__github__create_pull_request",
    ]
    assert r["reachable"] and r["path"][0] == "jira_issue" and r["path"][-1] == "pull_request"


def test_route_explicit_entities_and_project_filter(conn):
    r = queries.route(conn, src="url", to="screenshot")
    assert [s["tool"] for s in r["steps"]] == ["mcp__playwright__browser_navigate",
                                               "mcp__playwright__browser_take_screenshot"]
    # postgres is only enabled in shop-api
    assert queries.route(conn, to="rows", project="~/work/shop-api")["steps"][0]["tool"] == "mcp__postgres__query"
    in_other = queries.route(conn, to="rows", project="~/work/data-graph")["steps"]
    assert all("postgres" not in s["tool"] for s in in_other)


def test_route_without_target(conn):
    assert "error" in queries.route(conn, goal="hello there")


def test_blast_radius_github(conn):
    b = queries.blast_radius(conn, "github")
    assert len(b["lost_tools"]) == 23
    broken = {d["name"] for d in b["broken"]}
    assert "pr-from-ticket" in broken
    assert "user-settings#PreToolUse[1.0]" in broken      # the gitleaks hook only matches github tools
    assert "code-search" in {d["name"] for d in b["degraded"]}
    assert "pull_request" in {o["entity"] for o in b["orphaned_entities"]}
    assert set(b["projects"]) == {"~/work/shop-api", "~/work/data-graph"}


def test_blast_radius_plugin_server_and_unknown(conn):
    b = queries.blast_radius(conn, "plugin_oncall_sentry")
    assert b["plugins"] == ["oncall"]
    assert "triage-incident" in {d["name"] for d in b["broken"]}
    assert "error" in queries.blast_radius(conn, "nope")


def test_audit(conn):
    a = queries.audit(conn)
    assert {(d["name"], d["missing_server"]) for d in a["dangling"]} == {
        ("release-deploy", "linear"), ("standup-notes", "notion"), ("triage-incident", "pagerduty")}
    assert [h["matcher"] for h in a["dead_hooks"]] == ["mcp__linear__.*"]
    pairs = {(c["skill_a"], c["skill_b"]) for c in a["collisions"]}
    assert ("deploy-preview", "release-deploy") in pairs
    overlap_pairs = {(o["tool_a"], o["tool_b"]) for o in a["overlaps"]}
    assert ("mcp__git__git_create_branch", "mcp__github__create_branch") in overlap_pairs
    assert ("Write", "mcp__filesystem__write_file") in overlap_pairs
    assert {u["server"] for u in a["unused"]} == {"git", "memory"}


def test_minimal_context(conn):
    c = queries.minimal_context(conn, "fix the sentry error and open a pull request", k=6)
    tools = [t["tool"] for t in c["tools"]]
    assert len(tools) == 6
    assert "mcp__github__create_pull_request" in tools
    assert any("sentry" in t for t in tools)
    assert c["saved_pct"] > 80
