MATCH (t:Tool) WHERE NOT t.missing AND ($servers IS NULL OR t.server IN $servers)
RETURN count(t) AS tools, sum(t.tokens) AS tokens
