SHELL := /bin/sh
PYTHON ?= python3
NPM ?= npm
COMPOSE ?= docker compose

.PHONY: help bootstrap data-audit safety-check cluster-experiments preprocess phase3-demo evaluate build-ride-estimates load-db dev test e2e demo-check

help:
	@printf '%s\n' 'make bootstrap | data-audit | safety-check | dev | test'

bootstrap:
	$(PYTHON) scripts/bootstrap.py
	$(PYTHON) -m pip install --requirement backend/requirements-dev.txt
	$(PYTHON) -m pip install --requirement pipeline/requirements.txt
	$(NPM) --prefix frontend install

data-audit:
	$(PYTHON) scripts/data_audit.py

safety-check:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_tracking.ps1

dev:
	$(COMPOSE) up --build

test:
	$(PYTHON) -m pytest
	$(NPM) --prefix frontend run test:run
	$(NPM) --prefix frontend run build

cluster-experiments:
	$(PYTHON) scripts/cluster_experiments.py

preprocess:
	$(PYTHON) scripts/preprocess.py

phase3-demo:
	$(PYTHON) scripts/phase3_taipei_demo.py --stage all

evaluate:
	$(PYTHON) scripts/phase3_taipei_demo.py --stage all

build-ride-estimates:
	$(PYTHON) scripts/build_ride_estimates.py

load-db:
	$(PYTHON) scripts/build_ride_estimates.py
	$(PYTHON) scripts/load_db.py

e2e:
	$(NPM) --prefix frontend run e2e

demo-check:
	$(PYTHON) scripts/demo_check.py
