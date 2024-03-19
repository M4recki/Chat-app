from fastapi.testclient import TestClient
from project.python.main import app
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))

root_dir = os.path.abspath(os.path.join(current_dir, ".."))


client = TestClient(app)


def test_read_main():
    response = client.get("/")
    assert response.status_code == 200


def test_invalid_route():
    response = client.get("/invalid")
    assert response.status_code == 404


def test_unlogged_user():
    response = client.get("/search_user")
    assert response.status_code == 401
