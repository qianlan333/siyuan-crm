PYTHON ?= ./.venv310/bin/python

.PHONY: lint typecheck build check

lint:
	$(PYTHON) scripts/run_lint.py

typecheck:
	$(PYTHON) scripts/run_typecheck.py

build:
	$(PYTHON) -m pytest tests/test_deploy_workflow_contract.py tests/test_post_closeout_production_contract.py -q

check: lint typecheck build
