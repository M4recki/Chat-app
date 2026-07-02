from conftest import client

from project.python.database import async_url, get_db
from project.python.settings import settings as app_settings


def test_read_main():
    client.cookies.clear()
    response = client.get("/")
    assert response.status_code == 200


def test_invalid_route():
    response = client.get("/invalid")
    assert response.status_code == 404


#  settings properties


def test_settings_is_production():
    original = app_settings.environment
    app_settings.environment = "production"

    assert app_settings.is_production is True
    app_settings.environment = "development"
    assert app_settings.is_production is False
    app_settings.environment = original


def test_settings_is_testing():
    original = app_settings.environment
    app_settings.environment = "testing"

    assert app_settings.is_testing is True
    app_settings.testing = False
    app_settings.environment = "development"
    assert app_settings.is_testing is False
    app_settings.environment = original


#  database


def test_async_url_postgres():
    result = async_url("postgresql://user:pass@localhost/db")
    assert result == "postgresql+asyncpg://user:pass@localhost/db"


def test_async_url_sqlite():
    result = async_url("sqlite:///./test.db")
    assert result == "sqlite+aiosqlite:///./test.db"


def test_async_url_unknown():
    result = async_url("mysql://user:pass@localhost/db")
    assert result == "mysql://user:pass@localhost/db"


def test_get_db():
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass
