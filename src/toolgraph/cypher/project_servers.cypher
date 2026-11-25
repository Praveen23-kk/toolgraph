MATCH (s:Server)-[:ENABLED_IN]->(:Project {path: $project}) RETURN collect(s.id) AS servers
