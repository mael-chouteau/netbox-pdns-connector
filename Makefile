.PHONY: test lint format

test:
	python -m pytest -q

lint:
	ruff check src tests

format:
	ruff check --fix src tests