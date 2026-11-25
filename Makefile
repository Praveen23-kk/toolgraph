PY ?= python
TG = $(PY) -m toolgraph.cli

.PHONY: install demo ingest test audit mine serve clean

install:            ## install toolgraph + dev deps into the current environment
	$(PY) -m pip install -e ".[dev]"

demo:               ## ingest the fixture toolbox and answer route / blast radius / audit / context
	$(TG) demo

ingest:             ## rebuild data/toolgraph.rl from fixtures (the committed graph)
	$(TG) ingest --fixtures

test:
	$(PY) -m pytest -q

audit:
	$(TG) audit

mine:               ## build a graph of YOUR machine's toolbox in data/mine.rl (not committed)
	$(TG) -d data/mine.rl ingest
	$(TG) -d data/mine.rl audit

serve:              ## run the MCP server over stdio
	$(TG) serve

clean:
	rm -f data/mine.rl
