// Tools that disappear with the server.
MATCH (s:Server {id: $server})-[:PROVIDES]->(t:Tool)
RETURN t.id AS tool ORDER BY tool
