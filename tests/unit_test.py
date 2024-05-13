from conftest import client


def test_read_main():
    """
    Test the main route.

    Makes a GET request to the main '/' route
    and asserts a 200 response status code.
    """
    response = client.get("/")
    assert response.status_code == 200


def test_invalid_route():
    """
    Test an invalid route.

    Makes a GET request to an invalid route
    and asserts a 404 response status code.
    """

    response = client.get("/invalid")
    assert response.status_code == 404
