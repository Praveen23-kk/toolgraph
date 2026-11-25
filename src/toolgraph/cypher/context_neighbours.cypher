// Tools one entity-hop away from the seeds (they feed or consume what the seeds touch).
MATCH (s:Tool)-[:CONSUMES|PRODUCES]->(e:Entity)<-[:CONSUMES|PRODUCES]-(n:Tool)
WHERE s.id IN $seeds AND NOT n.id IN $seeds AND NOT e.generic AND NOT n.missing
  AND ($servers IS NULL OR n.server IN $servers)
RETURN n.id AS id, n.server AS server, n.tokens AS tokens, count(DISTINCT e) AS links
ORDER BY links DESC, tokens, id
LIMIT 20
