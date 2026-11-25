// Required inputs of one tool, and whether the tool also produces that entity (a name for a new thing).
MATCH (t:Tool {id: $id})-[c:CONSUMES]->(e:Entity)
WHERE c.required
RETURN e.name AS entity, e.generic AS generic, c.param AS param,
       EXISTS { (t)-[:PRODUCES]->(e) } AS self
ORDER BY entity
