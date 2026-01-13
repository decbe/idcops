.PHONY: install dev test lint format clean run

install:
	uv sync
	uv sync --extra dev

dev:
	uv run python manage.py runserver 0.0.0.0:8000

run:
	uv run gunicorn idcops.wsgi:application -c gunicorn.conf.py

test:
	uv run pytest tests/

test-cov:
	uv run pytest tests/ --cov=idcops --cov=dcrm --cov-report=term-missing

lint:
	uv run ruff check .

format:
	uv run ruff check --fix .
	uv run ruff format .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov

migrate:
	uv run python manage.py migrate

shell:
	uv run python manage.py shell

# Docker commands
docker-build:
	docker build -t idcops .

docker-run:
	docker run -p 8000:8000 --env-file .env idcops
