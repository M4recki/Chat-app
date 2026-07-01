from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from .helpers import decode_access_token
from .template import render_template

router = APIRouter()


@router.get("/")
def root(request: Request):
    """Render the home page.

    Authenticated users are redirected to the chat page.

    Args:
        request: The request object

    Returns:
        Response: Home page template or redirect to single_chat
    """
    user_id = decode_access_token(request.cookies)
    if user_id is not None:
        return RedirectResponse(request.url_for("single_chat"), status_code=303)
    return render_template("main_page.html", request)
