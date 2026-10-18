"""Business logic layer.

Routers (HTTP) → services (rules) → models (DB). Services know nothing
about HTTP requests, so the same logic is reused by the JSON API, the
HTML pages and the CLI.
"""
