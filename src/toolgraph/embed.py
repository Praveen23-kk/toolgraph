"""Optional vector index for hybrid (vector + full-text) tool retrieval.

Two embedders, both offline and key-free:
- ``hash``: feature hashing of word unigrams and bigrams (no download, deterministic; good for
  tests and CI, weaker semantics);
- ``fastembed``: a local ONNX model (BAAI/bge-small-en-v1.5, 384 dims) via ``pip install fastembed``;
  the model is downloaded once on first use and then runs fully offline.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Callable

from toolgraph.db import rows

HASH_DIMS = 256
_W = re.compile(r"[a-z0-9]+")


def hash_embedder(dims: int = HASH_DIMS) -> Callable[[str], list[float]]:
    def embed(text: str) -> list[float]:
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).replace("_", " ").lower()
        words = _W.findall(text)
        v = [0.0] * dims
        for gram in words + [a + " " + b for a, b in zip(words, words[1:])]:
            h = int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=8).digest(), "big")
            v[h % dims] += 1.0 if (h >> 63) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]
    embed.dims = dims  # type: ignore[attr-defined]
    embed.kind = "hash"  # type: ignore[attr-defined]
    return embed


def fastembed_embedder(model: str = "BAAI/bge-small-en-v1.5") -> Callable[[str], list[float]]:
    try:
        from fastembed import TextEmbedding
    except ImportError as e:  # pragma: no cover - optional dependency
        raise SystemExit("fastembed is not installed: pip install 'toolgraph[embed]' (or use --embed hash)") from e
    m = TextEmbedding(model_name=model)

    def embed(text: str) -> list[float]:
        return [float(x) for x in next(iter(m.embed([text])))]
    embed.dims = len(embed("probe"))  # type: ignore[attr-defined]
    embed.kind = "fastembed"  # type: ignore[attr-defined]
    return embed


def get_embedder(kind: str | None):
    if not kind:
        return None
    if kind == "hash":
        return hash_embedder()
    if kind == "fastembed":
        return fastembed_embedder()
    raise SystemExit(f"unknown embedder {kind!r}: use hash or fastembed")


def add_vectors(conn, embed) -> int:
    """Embed every installed tool and build the ``tool_vec`` vector index. Returns tools embedded."""
    tools = rows(conn, "MATCH (t:Tool) WHERE NOT t.missing RETURN t.id AS id, t.name AS name, t.description AS d ORDER BY id")
    batch = [{"id": t["id"], "v": embed(f"{t['name']}. {t['d']}")} for t in tools]
    dims = int(embed.dims)  # index DDL takes no parameters; this is an int we computed, not user input
    conn.execute("CREATE VECTOR INDEX tool_vec IF NOT EXISTS FOR (t:Tool) ON (t.embedding) "
                 f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dims}, `vector.similarity_function`: 'cosine'}}}}")
    conn.execute("UNWIND $batch AS r MATCH (t:Tool {id: r.id}) SET t.embedding = vector(r.v, $dims, FLOAT32)",
                 {"batch": batch, "dims": int(embed.dims)})
    conn.execute("MERGE (m:Meta {key: 'embedder'}) SET m.kind = $kind, m.dims = $dims",
                 {"kind": embed.kind, "dims": int(embed.dims)})
    return len(batch)


HYBRID = """
CALL () {
  MATCH (t:Tool)
  SEARCH t IN (VECTOR INDEX tool_vec FOR $qv LIMIT $k) SCORE AS score
  WITH t ORDER BY score DESC, t.id
  WITH collect(t) AS ts
  UNWIND range(0, size(ts) - 1) AS i
  RETURN ts[i] AS t, i + 1 AS rank
  UNION ALL
  MATCH (t:Tool)
  SEARCH t IN (FULLTEXT INDEX tool_text FOR $q LIMIT $k) SCORE AS score
  WITH t ORDER BY score DESC, t.id
  WITH collect(t) AS ts
  UNWIND range(0, size(ts) - 1) AS i
  RETURN ts[i] AS t, i + 1 AS rank
}
WITH t, sum(1.0 / (60 + rank)) AS rrf
RETURN t.id AS id, t.server AS server, rrf
ORDER BY rrf DESC, id
LIMIT $limit
"""


def hybrid_search(conn, text: str, embed, limit: int = 10, k: int = 25) -> list[dict]:
    from toolgraph.queries import _ft_query
    return rows(conn, HYBRID, {"qv": embed(text), "q": _ft_query(text), "k": k, "limit": limit})


def stored_embedder(conn):
    """The embedder the graph was built with, or None if it has no vectors."""
    meta = rows(conn, "MATCH (m:Meta {key: 'embedder'}) RETURN m.kind AS kind")
    return get_embedder(meta[0]["kind"]) if meta else None
