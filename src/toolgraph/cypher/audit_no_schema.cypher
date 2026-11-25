// Configured servers we have no tool list for (run `toolgraph capture` to fetch it).
MATCH (s:Server) WHERE NOT s.has_schema RETURN s.id AS server, s.command AS command ORDER BY server
