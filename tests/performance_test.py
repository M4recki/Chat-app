from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time
from fastapi.testclient import TestClient
from conftest import client
from project.python.main import app
from project.python.rate_limit import _rate_limiter


def test_rate_limiter_parallel_requests():
    _rate_limiter._buckets.clear()
    n_requests = 20
    results = []

    def make_request(_):
        response = client.get("/")
        return response.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(make_request, i) for i in range(n_requests)]
        results = [f.result() for f in as_completed(futures)]

    successes = [r for r in results if r == 200]
    rate_limited = [r for r in results if r == 429]
    assert len(successes) + len(rate_limited) == n_requests
    assert len(successes) > 0


def test_concurrent_signup():
    _rate_limiter._buckets.clear()
    n_users = 5
    users = []

    def signup(i):
        local = TestClient(app, follow_redirects=False)
        resp = local.post(
            "/sign_up",
            data={
                "name": f"Perf{i}",
                "surname": f"Test{i}",
                "email": f"perf{i}-{time.time_ns()}@example.com",
                "password": "StrongPass1",
                "confirm_password": "StrongPass1",
                "terms_conditions": "on",
            },
        )
        return i, resp.status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(signup, i) for i in range(n_users)]
        for f in as_completed(futures):
            users.append(f.result())

    ok = [u for u in users if u[1] == 303]
    assert len(ok) == n_users


def test_concurrent_login():
    _rate_limiter._buckets.clear()
    email = f"perf-login-{time.time_ns()}@example.com"

    reg_client = TestClient(app, follow_redirects=False)
    reg_client.post(
        "/sign_up",
        data={
            "name": "Perf", "surname": "Login",
            "email": email,
            "password": "Password123", "confirm_password": "Password123",
            "terms_conditions": "on",
        },
    )

    results = []
    def login(_):
        local = TestClient(app, follow_redirects=False)
        resp = local.post("/login", data={"email": email, "password": "Password123"})
        return resp.status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(login, i) for i in range(5)]
        results = [f.result() for f in as_completed(futures)]

    successes = [r for r in results if r == 303]
    assert len(successes) >= 1, f"concurrent_results={results}"


def test_websocket_multiple_broadcast():
    from tests.model_test import TestingSessionLocal
    from project.python.models import User
    from io import BytesIO
    from PIL import Image

    db = TestingSessionLocal()
    img_binary = BytesIO()
    with Image.open("project/static/img/default avatar.png") as img:
        img.save(img_binary, format="PNG")
    user = User(
        name="WS", surname="Perf", email="ws-perf@example.com",
        password="x", avatar=img_binary.getvalue(),
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()
    uid = user.id

    channels = [f"perf-ch-{i}" for i in range(3)]

    with TestClient(app) as local:
        for ch in channels:
            with local.websocket_connect(f"/ws/{ch}/TestUser/{uid}") as ws:
                ws.send_json({"channel_id": ch, "message": "ping"})
                data = ws.receive_text()
                assert "ping" in data

    db.close()


def test_endpoint_response_times():
    _rate_limiter._buckets.clear()
    endpoints = ["/", "/login", "/sign_up", "/contact"]
    max_time_ms = 500

    for ep in endpoints:
        start = time.perf_counter()
        response = client.get(ep)
        elapsed = (time.perf_counter() - start) * 1000
        assert response.status_code == 200, f"{ep} returned {response.status_code}"
        assert elapsed < max_time_ms, f"{ep} took {elapsed:.0f}ms (limit {max_time_ms}ms)"
