// Servers no skill, hook or CLAUDE.md ever points at, ranked by context they cost.
MATCH (s:Server)
WHERE s.scope <> 'builtin'
  AND NOT EXISTS { (s)-[:PROVIDES]->(:Tool)<-[:REQUIRES_TOOL|MATCHES|MENTIONS]-() }
RETURN s.id AS server, s.tool_count AS tools, s.tokens AS tokens
ORDER BY tokens DESC, server
