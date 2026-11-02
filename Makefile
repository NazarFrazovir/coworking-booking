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
        seed-sandbox lint test ci loadtest-seed loadtest-smoke \
        loadtest-baseline loadtest-stress loadtest-report \
        docker-up docker-dev docker-down docker-logs docker-admin

# Only the database (published on localhost) for running the app outside
# Docker. Uses the dev override, because the base file keeps the DB private.
DB_ONLY = docker compose -f docker-compose.yml -f docker-compose.dev.yml

db-sandbox:
	$(DB_ONLY) --env-file .env.sandbox -p cowork-sandbox up -d --wait db

db-production:
	$(DB_ONLY) --env-file .env.production -p cowork-production up -d --wait db

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

# ---------- load testing (lab #4) ----------
# Start the server first, in another terminal:
#   APP_ENV=sandbox DEBUG=false LOG_LEVEL=WARNING \
#     uvicorn app.main:app --port 8000 --workers 2 --no-access-log

LT_HOST ?= http://127.0.0.1:8000
LT_OUT = loadtest/results

loadtest-seed:
	APP_ENV=sandbox $(PY) -m loadtest.seed_users --users 300

loadtest-smoke:
	LOAD_PROFILE=smoke locust -f loadtest/locustfile.py --host $(LT_HOST) \
		--headless --only-summary

loadtest-baseline:
	$(PY) -m loadtest.monitor --out $(LT_OUT)/baseline_resources.csv --duration 245 &
	LOAD_PROFILE=baseline locust -f loadtest/locustfile.py --host $(LT_HOST) \
		--headless --only-summary --csv $(LT_OUT)/baseline --csv-full-history \
		--html $(LT_OUT)/baseline.html

loadtest-stress:
	$(PY) -m loadtest.monitor --out $(LT_OUT)/stress_resources.csv --duration 365 &
	LOAD_PROFILE=stress locust -f loadtest/locustfile.py --host $(LT_HOST) \
		--headless --only-summary --csv $(LT_OUT)/stress --csv-full-history \
		--html $(LT_OUT)/stress.html

loadtest-report:
	$(PY) -m loadtest.analyze

# ---------- Docker (lab #5) ----------
# cp config/.env.docker.example .env   (once)

docker-up:
	docker compose up --build -d --wait

docker-dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f app

docker-admin:
	docker compose exec app python -m app.cli create-admin --email admin@example.com --name "Admin"
