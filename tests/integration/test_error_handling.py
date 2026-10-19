"""Lab 3: DEBUG mode and what users see when something breaks."""

import logging
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import get_db
from app.main import create_app

STRONG_SECRET = "Vq3n0s7J1mXcA8pLr2Zt5Wy9Kd4Hf6Ge0Bu1Ni"
SECRET_DETAIL = "password=hunter2 at /srv/app/secret_module.py"
HTML = {"Accept": "text/html,application/xhtml+xml"}


def build(app_env: str, debug: bool, docs: bool = True) -> FastAPI:
    settings = Settings(
        _env_file=None,
        app_env=app_env,
        debug=debug,
        docs_enabled=docs,
        DATABASE_URL=f"sqlite:///coworking_{app_env}.db",
        jwt_secret_key=STRONG_SECRET,
    )
    return create_app(settings)


def _broken_db() -> Generator[None, None, None]:
    raise RuntimeError(SECRET_DETAIL)
    yield  # pragma: no cover


@pytest.fixture()
def production_client() -> Generator[TestClient, None, None]:
    app = build("production", debug=False, docs=False)
    app.dependency_overrides[get_db] = _broken_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_production_500_json_hides_internals(production_client: TestClient) -> None:
    r = production_client.get("/api/v1/spaces/")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    assert len(body["error_id"]) == 8
    assert "hunter2" not in r.text and "Traceback" not in r.text


def test_production_500_page_is_friendly(production_client: TestClient) -> None:
    r = production_client.get("/home", headers=HTML)
    assert r.status_code == 500
    assert "text/html" in r.headers["content-type"]
    assert "Щось пішло не так" in r.text and "Код помилки" in r.text
    for leak in ("hunter2", "Traceback", "RuntimeError", "secret_module.py"):
        assert leak not in r.text


def test_full_traceback_goes_to_log_with_same_error_id(
    production_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        r = production_client.get("/api/v1/spaces/")
    error_id = r.json()["error_id"]
    record = next(rec for rec in caplog.records if error_id in rec.getMessage())
    assert record.exc_info is not None
    assert SECRET_DETAIL in str(record.exc_info[1])


def test_sandbox_debug_shows_traceback_to_developer() -> None:
    app = build("sandbox", debug=True)
    app.dependency_overrides[get_db] = _broken_db
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/spaces/", headers=HTML)
    assert r.status_code == 500
    assert "RuntimeError" in r.text  # Starlette's debug page


def test_docs_are_disabled_in_production(production_client: TestClient) -> None:
    assert production_client.get("/docs").status_code == 404
    assert production_client.get("/openapi.json").status_code == 404


def test_html_404_page_and_json_404_for_api(production_client: TestClient) -> None:
    page = production_client.get("/no-such-page", headers=HTML)
    assert page.status_code == 404
    assert "Такої сторінки немає" in page.text
    api = production_client.get("/api/v1/no-such-endpoint", headers=HTML)
    assert api.status_code == 404
    assert api.json() == {"detail": "Not Found"}


def test_health_reports_environment(production_client: TestClient) -> None:
    assert production_client.get("/health").json()["environment"] == "production"
