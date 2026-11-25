// Entities that nothing else can produce once the server is gone, and the tools left stranded
// because they require one of those entities.
MATCH (s:Server {id: $server})-[:PROVIDES]->(:Tool)-[:PRODUCES]->(e:Entity)
WHERE NOT e.generic
  AND NOT EXISTS { MATCH (o:Tool)-[:PRODUCES]->(e) WHERE NOT o.missing AND o.server <> $server }
WITH DISTINCT e
OPTIONAL MATCH (st:Tool)-[c:CONSUMES]->(e)
  WHERE c.required AND st.server <> $server AND NOT EXISTS { (st)-[:PRODUCES]->(e) }
RETURN e.name AS entity, collect(DISTINCT st.id) AS stranded
ORDER BY entity
