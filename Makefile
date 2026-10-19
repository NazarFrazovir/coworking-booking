# Shortcuts for both environments. Every target sets APP_ENV explicitly,
# so it is always obvious which database a command touches.
#
#   make setup-sandbox     # DB + migrations + demo data
#   make run-sandbox       # http://127.0.0.1:8000 with auto-reload
#   make setup-production  # DB + migrations
#   make run-production    # no reload, no debug, 2 workers

PY ?= python

.PHONY: db-sandbox db-production migrate-sandbox migrate-production \
        setup-sandbox setup-production run-sandbox run-production \
        seed-sandbox lint test ci

db-sandbox:
	docker compose --env-file .env.sandbox -p cowork-sandbox up -d --wait

db-production:
	docker compose --env-file .env.production -p cowork-production up -d --wait

migrate-sandbox:
	APP_ENV=sandbox alembic upgrade head

migrate-production:
	APP_ENV=production alembic upgrade head

seed-sandbox:
	APP_ENV=sandbox $(PY) -m app.cli seed-demo

setup-sandbox: db-sandbox migrate-sandbox seed-sandbox

setup-production: db-production migrate-production

run-sandbox:
	APP_ENV=sandbox uvicorn app.main:app --reload --port 8000

run-production:
	APP_ENV=production uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2 --no-server-header

lint:
	ruff check .
	black --check .

test:
	pytest

ci: lint test
