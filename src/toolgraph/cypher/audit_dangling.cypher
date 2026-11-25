// Skills, hooks and CLAUDE.md files that reference tools no installed server provides.
MATCH (d)-[:REQUIRES_TOOL|MENTIONS]->(t:Tool)
WHERE NOT EXISTS { (:Server)-[:PROVIDES]->(t) }
RETURN labels(d)[0] AS kind, coalesce(d.name, d.id) AS name, t.id AS tool, t.server AS missing_server
ORDER BY kind, name, tool
