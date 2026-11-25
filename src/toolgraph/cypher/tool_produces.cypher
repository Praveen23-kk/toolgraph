MATCH (t:Tool {id: $id})-[:PRODUCES]->(e:Entity) RETURN collect(e.name) AS entities
