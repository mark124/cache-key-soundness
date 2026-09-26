# One target per paper artifact. Every target below runs offline from the
# committed files in data/. `make all` == `python -m cachekeys reproduce`.
PY ?= python

all: table1 table2 table3 table4 rq3

table1 table2:            ## sample, prevalence, key composition
	$(PY) scripts/analyze_sample.py
table3:                   ## controlled experiment outcomes (harm.yml runs)
	$(PY) scripts/collect_harm.py table
rq3:                      ## key changes mined from workflow history (Section 5.3)
	$(PY) scripts/mine_key_fixes.py table
table4:                   ## classifier vs hand labels
	$(PY) scripts/validate_classifier.py
test:
	$(PY) -m pytest -q tests

# --- network steps (not needed to reproduce the paper) ---------------------
fetch-sample:             ## GitHub search + GraphQL; needs a token
	$(PY) scripts/fetch_sample.py all
fetch-history:
	$(PY) scripts/mine_key_fixes.py fetch

.PHONY: all table1 table2 table3 table4 rq3 test fetch-sample fetch-history
