// Skills whose trigger phrases or text match the goal, and the installed tools they need.
MATCH (k:Skill)
SEARCH k IN (FULLTEXT INDEX skill_text FOR $q LIMIT 5) SCORE AS score
OPTIONAL MATCH (k)-[:REQUIRES_TOOL]->(t:Tool) WHERE NOT t.missing
RETURN k.name AS skill, score, collect(t.id) AS tools
ORDER BY score DESC, skill
