from conftest import client
from fastapi.testclient import TestClient

from project.python.main import app
from project.python.routes.helpers import generate_csrf_token


def test_validation_error_returns_422_json():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/login",
        data={"email": "test@example.com", "csrf_token": csrf_token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "validation"
    assert payload["status_code"] == 422


def test_validation_error_returns_422_html():
    csrf_token = generate_csrf_token(0)
    response = client.post(
        "/login",
        data={"email": "test@example.com", "csrf_token": csrf_token},
    )

    assert response.status_code == 422
    assert "text/html" in response.headers.get("content-type", "")


def test_unhandled_exception_returns_500_json(monkeypatch):
    monkeypatch.setattr(
        "project.python.routes.main_page.render_template",
        lambda *_a, **_kw: (_ for _ in ()).throw(Exception("unexpected error")),
    )
    local_client = TestClient(app, raise_server_exceptions=False)
    response = local_client.get(
        "/",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "server"
    assert payload["status_code"] == 500


def test_unhandled_exception_returns_500_html(monkeypatch):
    monkeypatch.setattr(
        "project.python.routes.main_page.render_template",
        lambda *_a, **_kw: (_ for _ in ()).throw(Exception("unexpected error")),
    )
    local_client = TestClient(app, raise_server_exceptions=False)
    response = local_client.get("/")

    assert response.status_code == 500
    assert "text/html" in response.headers.get("content-type", "")
