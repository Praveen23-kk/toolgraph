MATCH (s:Server {id: $server})
OPTIONAL MATCH (s)-[:ENABLED_IN]->(p:Project)
OPTIONAL MATCH (pl:Plugin)-[:BUNDLES]->(s)
RETURN s.scope AS scope, s.tool_count AS tools, s.tokens AS tokens,
       collect(DISTINCT p.path) AS projects, collect(DISTINCT pl.name) AS plugins
