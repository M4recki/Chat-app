from pathlib import Path

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
)


def prefers_json(request: Request) -> bool:
    """Determine if the client prefers a JSON response based on headers.

    Checks the 'X-Requested-With' header for AJAX requests and the
    'Accept' header for JSON content types.

    Args:
        request (Request): The incoming HTTP request

    Returns:
        bool: True if the client prefers JSON, False otherwise
    """
    requested_with = request.headers.get("X-Requested-With")
    if requested_with == "XMLHttpRequest":
        return True

    accept = request.headers.get("accept", "")
    return "application/json" in accept.lower()


async def http_exception_handler(
    request: Request, exc: Exception
):
    """Handle HTTP exceptions and return appropriate responses based on
    client preferences.

    Args:
        request (Request): The incoming HTTP request
        exc (StarletteHTTPException): The exception

    Returns:
        JSONResponse or HTMLResponse: A JSON response if the client
            prefers JSON, otherwise an HTML response rendered from a
            template
    """
    status_code = getattr(exc, "status_code", 500) or 500
    default_messages = {
        401: (
            "Unauthorized",
            "You need to sign in to access this page.",
            "Your session might have expired.",
            True,
        ),
        403: (
            "Access denied",
            "You do not have permission to view this page.",
            "If you believe this is a mistake, contact support.",
            False,
        ),
        404: (
            "Page not found",
            "We could not find the page you were looking for.",
            "Check the link or return to the home page.",
            False,
        ),
        429: (
            "Too many requests",
            "You have sent too many requests in a short time.",
            "Please wait a moment and try again.",
            False,
        ),
        500: (
            "Server error",
            "Something went wrong on our side.",
            "Please try again later.",
            False,
        ),
    }

    detail = getattr(exc, "detail", "Something went wrong.")
    title, message, hint, show_login = default_messages.get(
        status_code,
        (
            "Unexpected error",
            detail or "Something went wrong.",
            "Please try again later.",
            False,
        ),
    )
    headers = getattr(exc, "headers", None)

    if prefers_json(request):
        return JSONResponse(
            status_code=status_code,
            content={
                "error": "http",
                "status_code": status_code,
                "title": title,
                "message": message,
                "hint": hint,
            },
            headers=headers,
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "status_code": status_code,
            "title": title,
            "message": message,
            "hint": hint,
            "show_login": show_login,
        },
        status_code=status_code,
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: Exception):
    """Handle request validation errors and return appropriate responses
    based on client preferences.

    Args:
        request (Request): The incoming HTTP request
        exc (RequestValidationError): The validation error

    Returns:
        JSONResponse or HTMLResponse: A JSON response if the client
            prefers JSON, otherwise an HTML response rendered from a
            template
    """
    errors = exc.errors() if isinstance(exc, RequestValidationError) else str(exc)
    if prefers_json(request):
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation",
                "status_code": 422,
                "message": "Validation error",
                "details": errors,
            },
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "status_code": 422,
            "title": "Validation error",
            "message": "Some inputs were not valid.",
            "hint": "Please check the form and try again.",
            "show_login": False,
        },
        status_code=422,
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions and return appropriate responses
    based on client preferences.

    Args:
        request (Request): The incoming HTTP request
        exc (Exception): The exception

    Returns:
        JSONResponse or HTMLResponse: A JSON response if the client
            prefers JSON, otherwise an HTML response rendered from a
            template
    """
    if prefers_json(request):
        return JSONResponse(
            status_code=500,
            content={
                "error": "server",
                "status_code": 500,
                "message": "Unexpected server error. Please try again later.",
            },
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "status_code": 500,
            "title": "Server error",
            "message": "Unexpected server error. Please try again later.",
            "hint": "If the problem persists, contact support.",
            "show_login": False,
        },
        status_code=500,
    )
