from conftest import client


def test_read_main():
    """_summary_"""
    response = client.get("/")
    assert response.status_code == 200


def test_invalid_route():
    """_summary_"""
    response = client.get("/invalid")
    assert response.status_code == 404


def test_unlogged_user():
    """_summary_"""
    response = client.get("/search_user")
    assert response.status_code == 401
