CALL () { MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n }
RETURN label, n ORDER BY label
