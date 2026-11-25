// Shortest chain of tools that turns entity $from into entity $to.
// Each hop is (:Entity)<-[:CONSUMES]-(:Tool)-[:PRODUCES]->(:Entity).
MATCH p = SHORTEST 1 (a:Entity {name: $from})
      (()<-[:CONSUMES]-(t:Tool WHERE $servers IS NULL OR t.server IN $servers)-[:PRODUCES]->()){1,6}
      (b:Entity {name: $to})
RETURN [x IN t | x.id] AS tools, [n IN nodes(p) | coalesce(n.id, n.name)] AS chain
