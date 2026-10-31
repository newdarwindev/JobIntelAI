.PHONY: run check build
run:
	python -m uvicorn jobintel.app:app --host 127.0.0.1 --port 8000
check:
	python -m ruff check src tests
	python -m ruff format --check src tests
	python -m pytest -q
build:
	python -m build
