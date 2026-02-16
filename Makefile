.PHONY: setup test lint typecheck run dashboard clean

setup:
	python -m pip install -e ".[dev]"
	mkdir -p data logs
	cp -n .env.example .env 2>/dev/null || true
	alembic upgrade head

test:
	pytest

lint:
	ruff check src/ tests/

typecheck:
	mypy src/

format:
	ruff check --fix src/ tests/
	ruff format src/ tests/

run:
	python -m valuesentinel.cli

dashboard:
	streamlit run src/valuesentinel/dashboard/app.py

migrate:
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(msg)"

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	rm -rf data/valuesentinel.db logs/*.log __pycache__ .pytest_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
