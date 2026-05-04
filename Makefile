PYTHON ?= ./.venv310/bin/python

.PHONY: lint typecheck build test-customer-pulse test-customer-pulse-quality customer-pulse-quality customer-pulse-rollout-report customer-pulse-observation-status customer-pulse-observation-daily customer-pulse-observation-verdict check

lint:
	$(PYTHON) scripts/run_lint.py

typecheck:
	$(PYTHON) scripts/run_typecheck.py

build:
	$(PYTHON) scripts/run_build.py

test-customer-pulse:
	$(PYTHON) -m pytest -q tests/test_customer_pulse_inbox.py

test-customer-pulse-quality:
	$(PYTHON) -m pytest -q tests/test_customer_pulse_quality_gates.py

customer-pulse-quality:
	$(PYTHON) scripts/run_customer_pulse_quality_gates.py

customer-pulse-rollout-report:
	$(PYTHON) scripts/render_customer_pulse_rollout_report.py --days 7 --format markdown

customer-pulse-observation-status:
	$(PYTHON) scripts/run_customer_pulse_observation.py status

customer-pulse-observation-daily:
	$(PYTHON) scripts/run_customer_pulse_observation.py daily

customer-pulse-observation-verdict:
	$(PYTHON) scripts/run_customer_pulse_observation.py verdict

check: customer-pulse-quality
