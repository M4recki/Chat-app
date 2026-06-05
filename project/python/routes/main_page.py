from fastapi import APIRouter, Request

from .template import render_template

router = APIRouter()


@router.get("/")
def root(request: Request):
    """Render the home page.

    Args:
        request: The request object

    Returns:
        Response: Home page template response
    """
    return render_template("main_page.html", request)
