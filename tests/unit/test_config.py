"""Lab 3: configuration per environment.

Settings are built with ``_env_file=None`` (or a temp file) so these tests
never read the developer's real .env.sandbox / .env.production.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

import app.config as config_module
from app.config import ConfigError, Settings, load_settings

STRONG_SECRET = "Vq3n0s7J1mXcA8pLr2Zt5Wy9Kd4Hf6Ge0Bu1Ni"


def make(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "DATABASE_URL": "sqlite://",
        "jwt_secret_key": STRONG_SECRET,
        "debug": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Remove every variable Settings reads (conftest's, CI's, the shell's),
    so a test sees only what it sets itself."""
    for name, field in Settings.model_fields.items():
        monkeypatch.delenv(name.upper(), raising=False)
        if field.alias:
            monkeypatch.delenv(field.alias, raising=False)
    return monkeypatch


# ---------- no hardcoded secrets ----------


def test_jwt_secret_has_no_default(clean_env) -> None:
    with pytest.raises(ValidationError, match="jwt_secret_key"):
        Settings(_env_file=None, app_env="sandbox", DATABASE_URL="sqlite://")


def test_database_must_be_configured(clean_env) -> None:
    with pytest.raises(ValidationError, match="Database is not configured"):
        Settings(_env_file=None, app_env="sandbox", jwt_secret_key=STRONG_SECRET)


def test_secret_is_masked_in_repr_and_logs(clean_env) -> None:
    s = make(
        DATABASE_URL="postgresql://u:SuperSecretPw@db:5432/coworking_sandbox",
        app_env="sandbox",
    )
    assert STRONG_SECRET not in repr(s)
    assert "SuperSecretPw" not in s.safe_database_url
    assert "***" in s.safe_database_url


# ---------- reading .env.<APP_ENV> files ----------


def test_env_file_is_chosen_by_app_env(clean_env, tmp_path: Path) -> None:
    (tmp_path / ".env.sandbox").write_text(
        "POSTGRES_DB=coworking_sandbox\nPOSTGRES_USER=sb\nPOSTGRES_PASSWORD=pw1\n"
        "POSTGRES_PORT=5435\nJWT_SECRET_KEY=sandbox-key\nDEBUG=true\n"
    )
    (tmp_path / ".env.production").write_text(
        "POSTGRES_DB=coworking_production\nPOSTGRES_USER=pr\nPOSTGRES_PASSWORD=pw2\n"
        f"POSTGRES_PORT=5436\nJWT_SECRET_KEY={STRONG_SECRET}\nDEBUG=false\n"
    )
    clean_env.setattr(config_module, "PROJECT_ROOT", tmp_path)

    sandbox = load_settings("sandbox")
    production = load_settings("production")

    assert sandbox.debug is True
    assert sandbox.database_url_obj.database == "coworking_sandbox"
    assert sandbox.database_url_obj.port == 5435
    assert production.debug is False
    assert production.database_url_obj.database == "coworking_production"
    assert production.database_url_obj.port == 5436


def test_real_env_vars_override_the_file(clean_env, tmp_path: Path) -> None:
    """Cloud hosting / CI inject variables; they win over the file."""
    (tmp_path / ".env.sandbox").write_text(
        "DATABASE_URL=postgresql://a:b@localhost/coworking_sandbox\n"
        "JWT_SECRET_KEY=from-file\nLOG_LEVEL=DEBUG\n"
    )
    clean_env.setattr(config_module, "PROJECT_ROOT", tmp_path)
    clean_env.setenv("LOG_LEVEL", "WARNING")
    assert load_settings("sandbox").log_level == "WARNING"


def test_unknown_app_env_is_rejected() -> None:
    with pytest.raises(ConfigError, match="Unknown APP_ENV"):
        load_settings("staging-typo")


def test_config_error_never_echoes_secret_values(clean_env, tmp_path: Path) -> None:
    (tmp_path / ".env.production").write_text(
        "DATABASE_URL=postgresql://u:TopSecretDbPw@h/coworking_production\n"
        "JWT_SECRET_KEY=change-me\nDEBUG=true\n"
    )
    clean_env.setattr(config_module, "PROJECT_ROOT", tmp_path)
    with pytest.raises(ConfigError) as info:
        load_settings("production")
    message = str(info.value)
    assert "DEBUG must be false" in message
    assert "TopSecretDbPw" not in message and "change-me" not in message
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_cloud_style_postgres_url_gets_driver() -> None:
    s = make(DATABASE_URL="postgres://u:p@host:5432/coworking_production")
    assert s.database_url_obj.drivername == "postgresql+psycopg2"


# ---------- production safety ----------


def test_production_refuses_debug() -> None:
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        make(app_env="production", debug=True)


@pytest.mark.parametrize(
    "weak", ["change-me", "short", "my-example-secret-value-1234567890"]
)
def test_production_refuses_weak_jwt_secret(weak: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        make(app_env="production", jwt_secret_key=weak)


def test_sandbox_allows_debug_and_simple_secret() -> None:
    s = make(app_env="sandbox", debug=True, jwt_secret_key="dev")
    assert s.debug and not s.is_production


# ---------- database isolation ----------


@pytest.mark.parametrize("db", ["coworking_sandbox", "coworking_test", "cowork_dev"])
def test_production_cannot_use_sandbox_or_test_db(db: str) -> None:
    with pytest.raises(ValidationError, match="Production must not use"):
        make(app_env="production", DATABASE_URL=f"postgresql://u:p@h/{db}")


def test_sandbox_cannot_use_production_db() -> None:
    with pytest.raises(ValidationError, match="Sandbox must not use"):
        make(app_env="sandbox", DATABASE_URL="postgresql://u:p@h/coworking_production")


def test_tests_never_use_a_real_database() -> None:
    """conftest forces the test env before the app is imported."""
    from app.config import settings
    from app.database import engine

    assert settings.app_env == "test"
    assert engine.url.drivername == "sqlite"
