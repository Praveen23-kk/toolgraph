"""Deterministic entity inference from JSON-schema property names and descriptions.

No model, no keys: a synonym map over normalised property names gives CONSUMES edges, and
phrase rules over the "Returns ..." part of a description give PRODUCES edges. The rules are
deliberately small and readable so a wrong edge is easy to explain and fix.
"""
from __future__ import annotations

import re

# Entities that are cheap to supply by hand (a title, a search string). They can bridge a
# route but are flagged so answers can say "you'll need to provide this text".
GENERIC = {"text", "search_query"}

# normalised property name -> entity
PARAM_ENTITY: dict[str, str] = {
    "owner": "repository", "repo": "repository", "repository": "repository",
    "path": "file_path", "filepath": "file_path", "paths": "file_path", "files": "file_path",
    "source": "file_path", "destination": "file_path",
    "branch": "branch", "head": "branch", "base": "branch", "branchname": "branch",
    "basebranch": "branch", "frombranch": "branch",
    "sha": "commit", "revision": "commit", "target": "commit",
    "pullnumber": "pull_request",
    "issuenumber": "github_issue",
    "issueidorkey": "jira_issue", "jql": "search_query", "cql": "search_query",
    "cloudid": "atlassian_site", "projectkey": "jira_project", "pageid": "confluence_page",
    "channelid": "slack_channel", "threadts": "slack_message", "timestamp": "slack_message",
    "userid": "slack_user",
    "sql": "sql_query",
    "url": "url",
    "repopath": "local_repo",
    "libraryname": "library_name", "context7compatiblelibraryid": "library_id",
    "ref": "page_element", "element": "page_element",
    "organizationslug": "sentry_org", "projectslug": "sentry_project", "issueid": "sentry_issue",
    "title": "text", "body": "text", "text": "text", "content": "text", "summary": "text",
    "commentbody": "text", "description": "text",
    "q": "search_query", "query": "search_query", "naturallanguagequery": "search_query", "pattern": "search_query",
    "entities": "kg_entity", "names": "kg_entity", "entitynames": "kg_entity",
}

# Server-specific overrides where a generic name means something specific.
SERVER_PARAM_ENTITY: dict[tuple[str, str], str] = {
    ("neo4j-cypher", "query"): "cypher_query",
    ("memory", "query"): "search_query",
    ("builtin", "command"): "shell_command",
    ("builtin", "prompt"): "text",
}

# (regex over the "produces" region, entity) - first qualified match wins over the generic one.
PRODUCE_RULES: list[tuple[str, str]] = [
    (r"pull requests?\b", "pull_request"),
    (r"\bjira issues?\b", "jira_issue"),
    (r"\bsentry issues?\b", "sentry_issue"),
    (r"\bsentry projects?\b", "sentry_project"),
    (r"\borganizations?\b", "sentry_org"),
    (r"(?<!jira )(?<!sentry )\bissues?\b", "github_issue"),
    (r"\brepositor(y|ies)\b", "repository"),
    (r"\bbranch(es)?\b", "branch"),
    (r"\bcommits?\b|\bdiff\b", "commit"),
    (r"\bfile paths?\b|\bthe file path\b|\bdirectory\b", "file_path"),
    (r"\bchannels?\b", "slack_channel"),
    (r"\bmessages?\b(?! text)", "slack_message"),
    (r"\busers?\b", "slack_user"),
    (r"\brows\b", "rows"),
    (r"\bgraph schema\b", "graph_schema"),
    (r"\bpage snapshot\b", "page_element"),
    (r"\bscreenshot\b", "screenshot"),
    (r"\blibrary id\b", "library_id"),
    (r"\bdocumentation\b", "text"),
    (r"\bcloud id\b", "atlassian_site"),
    (r"\bconfluence pages?\b", "confluence_page"),
    (r"\burls?\b", "url"),
    (r"\btext\b|\bmarkdown\b|\bcontents?\b|\bcomments?\b|\breview\b", "text"),
]

_REGION = re.compile(r"(returns?\b.*|including\b.*|extracts?\b.*|\bas (text|markdown)\b.*)", re.I | re.S)

# Phrase aliases so a plain-English goal can name entities.
GOAL_ALIASES: list[tuple[str, str]] = [
    (r"\bpull requests?\b|\bprs?\b", "pull_request"),
    (r"\bjira (ticket|issue)s?\b|\btickets?\b", "jira_issue"),
    (r"\bsentry (issue|error)s?\b|\bincidents?\b|\berrors?\b|\bexceptions?\b", "sentry_issue"),
    (r"\bgithub issues?\b|\bissues?\b", "github_issue"),
    (r"\brepo(sitory|sitories|s)?\b", "repository"),
    (r"\bbranch(es)?\b", "branch"),
    (r"\bcommits?\b|\bdiffs?\b", "commit"),
    (r"\bfiles?\b", "file_path"),
    (r"\bslack\b|\bchannels?\b", "slack_channel"),
    (r"\burls?\b|\bweb ?pages?\b|\bwebsites?\b", "url"),
    (r"\bscreenshots?\b", "screenshot"),
    (r"\bdocs\b|\bdocumentation\b", "library_id"),
    (r"\bsql\b|\bpostgres\b|\btables?\b", "sql_query"),
    (r"\bcypher\b|\bneo4j\b|\bgraph schema\b", "cypher_query"),
    (r"\blocal (git )?repo\b|\bworking tree\b", "local_repo"),
]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def consumes(server: str, tool: dict) -> list[tuple[str, bool, str]]:
    """Return [(entity, required, param)] for a tool's input schema."""
    schema = tool.get("inputSchema") or {}
    required = set(schema.get("required") or [])
    out: dict[str, tuple[str, bool, str]] = {}
    for prop in (schema.get("properties") or {}):
        ent = SERVER_PARAM_ENTITY.get((server, prop)) or SERVER_PARAM_ENTITY.get((server, _norm(prop))) \
            or PARAM_ENTITY.get(_norm(prop))
        if not ent:
            continue
        req = prop in required
        if ent not in out or (req and not out[ent][1]):
            out[ent] = (ent, req, prop)
    return sorted(out.values())


def produces(tool: dict) -> list[str]:
    desc = tool.get("description") or ""
    m = _REGION.search(desc)
    if not m:
        return []
    region = m.group(0).lower()
    found: list[str] = []
    for pattern, ent in PRODUCE_RULES:
        if re.search(pattern, region):
            if ent == "github_issue" and {"jira_issue", "sentry_issue"} & set(found):
                continue
            found.append(ent)
    return sorted(set(found))


def goal_entities(goal: str) -> list[tuple[int, str]]:
    """(position, entity) for every entity alias in a goal string, in order of appearance."""
    text = goal.lower()
    hits: dict[str, int] = {}
    taken: list[tuple[int, int]] = []
    for pattern, ent in GOAL_ALIASES:
        for m in re.finditer(pattern, text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            hits.setdefault(ent, m.start())
    return sorted((pos, ent) for ent, pos in hits.items())


def parse_goal(goal: str) -> dict:
    """Split a goal into from / to / have entities with a few positional rules.

    "open a PR on my repo from a Jira ticket" -> to=pull_request, have=[repository], from=jira_issue
    """
    text = goal.lower()
    ents = goal_entities(goal)
    src, tgt, have, rest = None, None, [], []
    for pos, ent in ents:
        before = text[max(0, pos - 24):pos]
        if src is None and re.search(r"\b(from|given|using)\b(\s+(my|the|a|an|our|this))?\s*$", before):
            src = ent
        elif re.search(r"\b(on|in|for|into)\b(\s+(my|the|a|an|our|this))?\s*$", before):
            have.append(ent)
        elif re.search(_MAKE + r"(\s+(me|us))?(\s+(my|the|a|an|our|this|new))?\s*$", before):
            tgt = ent  # the last thing we are asked to make wins
        else:
            rest.append(ent)
    if tgt is None and rest:
        tgt = rest.pop()
    if src is None and rest:
        src = rest.pop(0)
    have += rest
    if tgt in have:
        have.remove(tgt)
    return {"from": src, "to": tgt, "have": have}


_MAKE = r"\b(open|create|make|post|send|write|file|raise|take|draft|merge|get|find|produce|build|start|push)\b"
