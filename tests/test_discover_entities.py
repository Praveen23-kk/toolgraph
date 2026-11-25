from toolgraph.discover import trigger_phrases
from toolgraph.entities import consumes, parse_goal, produces


def test_discovers_every_scope(box):
    scopes = {s.id: s.scope for s in box.servers.values()}
    assert scopes["github"] == "user"
    assert scopes["postgres"] == "project"            # from ~/.claude.json projects
    assert scopes["neo4j-cypher"] == "project"        # from the project's .mcp.json
    assert scopes["plugin_oncall_sentry"] == "plugin"  # plugin servers get Claude Code's prefixed id
    assert scopes["builtin"] == "builtin"
    assert {s.scope for s in box.skills} == {"user", "plugin", "project"}
    assert len(box.hooks) == 5 and len(box.instructions) == 2


def test_consumes_maps_param_names():
    tool = {"name": "create_pull_request", "inputSchema": {"properties": {
        "owner": {}, "repo": {}, "title": {}, "head": {}, "base": {}, "draft": {}},
        "required": ["owner", "repo", "title", "head", "base"]}}
    ents = {e: req for e, req, _ in consumes("github", tool)}
    assert ents == {"repository": True, "text": True, "branch": True}


def test_server_specific_override():
    tool = {"name": "read_neo4j_cypher", "inputSchema": {"properties": {"query": {}}, "required": ["query"]}}
    assert consumes("neo4j-cypher", tool)[0][0] == "cypher_query"


def test_produces_uses_returns_clause_and_qualifiers():
    assert produces({"description": "Create a new pull request. Returns the pull request"}) == ["pull_request"]
    assert produces({"description": "Search Jira issues using JQL. Returns Jira issues"}) == ["jira_issue"]
    assert produces({"description": "Shows the working tree status"}) == []


def test_parse_goal():
    assert parse_goal("I want to open a PR on my repo from a Jira ticket") == \
        {"from": "jira_issue", "to": "pull_request", "have": ["repository"]}
    g = parse_goal("fix the sentry error and open a pull request")
    assert (g["from"], g["to"]) == ("sentry_issue", "pull_request")


def test_trigger_phrases():
    assert trigger_phrases('Use when the user says "deploy", "Ship It" or "x"') == ["deploy", "ship it"]
