from pathlib import Path

import pytest

from toolgraph import db
from toolgraph.discover import discover
from toolgraph.ingest import ingest

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "fixtures" / "home"
SCHEMAS = ROOT / "fixtures" / "servers"


@pytest.fixture(scope="session")
def box():
    return discover(HOME, SCHEMAS)


@pytest.fixture(scope="session")
def store(box, tmp_path_factory):
    path = tmp_path_factory.mktemp("tg") / "toolgraph.rl"
    ingest(box, path)
    return path


@pytest.fixture()
def conn(store):
    with db.open_store(store, read_only=True) as c:
        yield c
