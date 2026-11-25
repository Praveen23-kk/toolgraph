// Tools on different servers that do the same job (shared entities + similar wording).
MATCH (a:Tool)-[o:OVERLAPS_WITH]->(b:Tool)
RETURN a.id AS tool_a, b.id AS tool_b, o.score AS score, o.shared AS shared
ORDER BY score DESC, tool_a, tool_b
