// Cheapest tools that produce $entity: fewest required inputs we do not already have.
MATCH (t:Tool)-[:PRODUCES]->(:Entity {name: $entity})
WHERE NOT t.missing AND ($servers IS NULL OR t.server IN $servers) AND NOT t.id IN $exclude
OPTIONAL MATCH (t)-[c:CONSUMES]->(need:Entity)
  WHERE c.required AND need.name <> $entity AND NOT need.name IN $have AND NOT need.generic
WITH t, collect(need.name) AS needs
RETURN t.id AS id, t.server AS server, size(needs) AS unmet, needs, t.tokens AS tokens
ORDER BY unmet, CASE WHEN t.server = $prefer THEN 0 ELSE 1 END, tokens, id
LIMIT 5
