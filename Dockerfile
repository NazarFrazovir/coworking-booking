#
# CoWork Booking — multi-stage image.
#
#   builder  — compilers + pip: builds all dependencies into /opt/venv
#   base     — clean slim image: only the venv, the code and a non-root user
#   dev      — base + test tools, server with --reload (code bind-mounted)
#   runtime  — base + production server command (default, last stage)
#
#   docker build -t coworking-booking .              # runtime image
#   docker build --target dev -t coworking-booking:dev .

ARG PYTHON_IMAGE=python:3.12-slim

# ---------------------------------------------------------------- builder
# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE} AS builder
WORKDIR /build

# Build tools are only needed when a dependency has to be compiled from
# source (no wheel for the platform). They stay in this stage and never
# reach the final image, so their exact versions are not pinned.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Only the requirements file first: this layer is rebuilt only when the
# dependencies change, not on every code edit.
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements.txt

# ------------------------------------------------------------------- base
# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=sandbox

# Never run the app as root inside the container.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app app ./app
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

ENTRYPOINT ["entrypoint.sh"]

# -------------------------------------------------------------------- dev
FROM base AS dev

COPY --from=builder /build/requirements.txt /build/requirements-dev.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && rm /tmp/requirements*.txt

USER app
# The code is bind-mounted from the host (docker-compose.dev.yml), so the
# server restarts on every saved file without rebuilding the image.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app"]

# ---------------------------------------------------------------- runtime
FROM base AS runtime

USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-server-header"]
