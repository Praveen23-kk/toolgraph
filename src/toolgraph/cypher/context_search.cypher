// Full-text candidates for a goal.
MATCH (t:Tool)
SEARCH t IN (FULLTEXT INDEX tool_text FOR $q LIMIT 40) SCORE AS score
WITH t, score WHERE NOT t.missing AND ($servers IS NULL OR t.server IN $servers)
RETURN t.id AS id, t.server AS server, t.tokens AS tokens, score
ORDER BY score DESC, id
