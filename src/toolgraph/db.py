"""Thin helpers around the Relate Python binding (``pip install relate-db``, ``import relate``).

Rules this module enforces for the rest of the package:
- parameters are always passed as ``$name`` dict params, never interpolated into Cypher;
- one writer per store: readers open ``read_only=True`` (a .rl file cannot be opened read-only
  while a writer holds it, so ingest must finish before queries run);
- connections are single-thread: open, use, close.
"""
from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path

import relate

DEFAULT_DB = os.environ.get("TOOLGRAPH_DB", "data/toolgraph.rl")


def open_store(path: str | Path = DEFAULT_DB, read_only: bool = False):
    path = str(path)
    if path != ":memory:" and not read_only:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    if read_only and path != ":memory:" and not Path(path).exists():
        raise FileNotFoundError(f"no graph at {path} - run `toolgraph ingest` first")
    return relate.connect(path, read_only=read_only)


def remove_store(path: str | Path) -> None:
    p = Path(str(path))
    if str(path) == ":memory:" or not p.exists():
        return
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()


def rows(conn, query: str, params: dict | None = None) -> list[dict]:
    return [dict(r) for r in conn.execute(query, params or {})]


def cypher(name: str) -> str:
    """Load a named query from the packaged ``cypher/`` folder."""
    return resources.files("toolgraph").joinpath("cypher", f"{name}.cypher").read_text(encoding="utf-8")
