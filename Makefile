.PHONY: setup api api-offline ui test lint eval report offline-eval

PYTHON := .venv/bin/python

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -e '.[dev,ui,llm]'

api:
	$(PYTHON) -m uvicorn app.main:app --reload

api-offline:
	REASONER_MODE=extractive PIPELINE_MODE=baseline $(PYTHON) -m uvicorn app.main:app --reload

ui:
	API_BASE_URL=http://localhost:8000 $(PYTHON) -m streamlit run ui/app.py

test:
	$(PYTHON) -m pytest

lint:
	.venv/bin/ruff check .

eval:
	curl -s -X POST http://localhost:8000/v1/evaluations/run

report:
	$(PYTHON) -m scripts.export_report --output reports/baseline-$$(date -u +%Y%m%dT%H%M%SZ)

offline-eval:
	$(PYTHON) -m scripts.offline_eval --output reports/offline-$$(date -u +%Y%m%dT%H%M%SZ)
