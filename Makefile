PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
ARGS ?=
PROJECT ?=
SCENARIO ?= success

.PHONY: help setup migrate demo serve quality check check-postgres prepare-offline env emulator-scenario acquisition-check acquisition-public-check model-prepare model-check experiment-replay experiment-rescore experiment-audit experiment-publish experiment-resume network-experiment reports catalogue-check ui-install ui-check docs-check

help:
	$(PYTHON) -m scripts.tasks --help
setup:
	python3 -m scripts.tasks setup
migrate:
	$(PYTHON) -m scripts.tasks migrate
demo:
	$(PYTHON) -m scripts.tasks demo
serve:
	$(PYTHON) -m scripts.serve_ui $(ARGS)
quality:
	$(PYTHON) -m scripts.tasks quality
check: quality
	$(PYTHON) scripts/check.py $(ARGS)
check-postgres: quality
	$(PYTHON) -m scripts.task_postgres $(ARGS)
prepare-offline:
	$(PYTHON) -m scripts.tasks prepare-offline $(ARGS)
env:
	$(PYTHON) -m scripts.environment $(ARGS)
emulator-scenario:
	$(PYTHON) -m scripts.task_emulator --project "$(PROJECT)" --scenario "$(SCENARIO)"
acquisition-check:
	$(PYTHON) -m scripts.acquisition_smoke $(ARGS)
acquisition-public-check:
	$(PYTHON) -m scripts.acquisition_public_smoke $(ARGS)
model-prepare:
	$(PYTHON) -m scripts.local_model $(ARGS)
model-check:
	$(PYTHON) -m scripts.local_smoke $(ARGS)
experiment-replay:
	$(PYTHON) -m scripts.task_experiment $(ARGS)
experiment-rescore:
	$(PYTHON) -m jobintel.cli experiment rescore $(ARGS)
experiment-audit:
	$(PYTHON) -m jobintel.cli experiment audit $(ARGS)
experiment-publish:
	$(PYTHON) -m jobintel.cli experiment publish $(ARGS)
experiment-resume:
	$(PYTHON) -m jobintel.cli experiment resume $(ARGS)
network-experiment:
	$(PYTHON) -m scripts.network_experiments $(ARGS)
reports:
	$(PYTHON) -m scripts.task_reports $(ARGS)
catalogue-check:
	$(PYTHON) -m scripts.tasks catalogue-check $(ARGS)
ui-install:
	$(PYTHON) -m scripts.tasks ui-install
ui-check:
	$(PYTHON) -m scripts.tasks ui-check
docs-check:
	$(PYTHON) -m scripts.check_docs
