// Two or more skills that fire on the same phrase, or on phrases where one contains the other.
MATCH (a:Skill)-[:TRIGGERS_ON]->(ka:Keyword), (b:Skill)-[:TRIGGERS_ON]->(kb:Keyword)
WHERE a.id < b.id AND (ka.text = kb.text OR ka.text CONTAINS kb.text OR kb.text CONTAINS ka.text)
  AND size(ka.text) >= 4 AND size(kb.text) >= 4
WITH a, b, collect(DISTINCT CASE WHEN ka.text = kb.text THEN ka.text ELSE ka.text + ' ~ ' + kb.text END) AS phrases
RETURN a.id AS skill_a, b.id AS skill_b, a.name = b.name AS same_name, phrases, size(phrases) AS shared
ORDER BY shared DESC, skill_a, skill_b
