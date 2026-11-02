#!/bin/sh
# Container entrypoint: bring the database schema up to date, then start
# whatever command was given (uvicorn by default, see Dockerfile CMD).
#
# The database is already healthy at this point: docker compose starts the
# app only after the db healthcheck passes (depends_on: service_healthy).
set -e

echo "[entrypoint] APP_ENV=${APP_ENV}: applying database migrations"
alembic upgrade head

if [ "${SEED_DEMO:-false}" = "true" ] && [ "${APP_ENV}" = "sandbox" ]; then
    echo "[entrypoint] seeding demo data (sandbox only)"
    python -m app.cli seed-demo || echo "[entrypoint] demo data already present"
fi

exec "$@"
