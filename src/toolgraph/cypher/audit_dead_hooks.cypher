// Hooks with a matcher that matches no installed tool.
MATCH (h:Hook)
WHERE h.matcher IS NOT NULL AND NOT EXISTS { (h)-[:MATCHES]->(:Tool) }
RETURN h.id AS hook, h.event AS event, h.matcher AS matcher, h.command AS command
ORDER BY hook
