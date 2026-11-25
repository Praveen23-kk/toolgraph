// Everything that points at one of the server's tools: skills, hooks, CLAUDE.md files,
// plus the plugin that ships them (variable-length BUNDLES hop of 0..1).
MATCH (s:Server {id: $server})-[:PROVIDES]->(t:Tool)<-[r:REQUIRES_TOOL|MATCHES|MENTIONS]-(d)
WITH d, type(r) AS via, collect(DISTINCT t.id) AS lost
OPTIONAL MATCH (d)-[:REQUIRES_TOOL|MATCHES|MENTIONS]->(other:Tool) WHERE NOT other.missing
WITH d, via, lost, collect(DISTINCT other.id) AS uses
OPTIONAL MATCH (pl:Plugin)-[:BUNDLES*0..1]->(d)
RETURN labels(d)[0] AS kind, coalesce(d.name, d.id) AS name, d.id AS id, via, lost,
       size(lost) AS lost_count, size(uses) AS total, size(lost) = size(uses) AS dead,
       collect(DISTINCT pl.name) AS plugins
ORDER BY dead DESC, kind, name
