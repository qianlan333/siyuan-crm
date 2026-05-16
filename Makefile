PYTHON ?= ./.venv310/bin/python

.PHONY: lint typecheck build check

lint:
	$(PYTHON) scripts/run_lint.py

typecheck:
	$(PYTHON) scripts/run_typecheck.py

build:
	$(PYTHON) scripts/run_build.py

check: lint typecheck build
