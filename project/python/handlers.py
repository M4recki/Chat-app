from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
)


@dataclass
class ErrorTemplate:
    title: str
    message: str
    hint: str
    show_login: bool = False


DEFAULT_ERRORS: dict[int, ErrorTemplate] = {
    401: ErrorTemplate(
        "Unauthorized",
        "You need to sign in to access this page.",
        "Your session might have expired.",
        True,
    ),
    403: ErrorTemplate(
        "Access denied",
        "You do not have permission to view this page.",
        "If you believe this is a mistake, contact support.",
    ),
    404: ErrorTemplate(
        "Page not found",
        "We could not find the page you were looking for.",
        "Check the link or return to the home page.",
    ),
    429: ErrorTemplate(
        "Too many requests",
        "You have sent too many requests in a short time.",
        "Please wait a moment and try again.",
    ),
    500: ErrorTemplate(
        "Server error",
        "Something went wrong on our side.",
        "Please try again later.",
    ),
}


def prefers_json(request: Request) -> bool:
    """Determine if the client prefers a JSON response based on headers.

    Checks the 'X-Requested-With' header for AJAX requests and the
    'Accept' header for JSON content types.

    Args:
        request: The incoming HTTP request

    Returns:
        bool: True if the client prefers JSON, False otherwise
    """
    requested_with = request.headers.get("X-Requested-With")
    if requested_with == "XMLHttpRequest":
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept.lower()


def build_json_response(
    status_code: int, error_type: str, headers: dict | None = None, **extra: object
) -> JSONResponse:
    """Build a JSON error response.

    Args:
        status_code: HTTP status code
        error_type: Short error type identifier
        headers: Optional HTTP headers
        extra: Additional fields to include in the JSON body

    Returns:
        JSONResponse: A FastAPI JSON response
    """
    return JSONResponse(
        status_code=status_code,
        content={"error": error_type, "status_code": status_code, **extra},
        headers=headers,
    )


def build_html_response(
    request: Request,
    status_code: int,
    error: ErrorTemplate,
    headers: dict | None = None,
):
    """Build an HTML error response from a template.

    Args:
        request: The incoming HTTP request
        status_code: HTTP status code
        error: An ErrorTemplate with title, message, hint, show_login
        headers: Optional HTTP headers

    Returns:
        TemplateResponse: A FastAPI template response
    """
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "status_code": status_code,
            "title": error.title,
            "message": error.message,
            "hint": error.hint,
            "show_login": error.show_login,
        },
        status_code=status_code,
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: Exception):
    """Handle HTTP exceptions and return appropriate responses based on
    client preferences.

    Args:
        request: The incoming HTTP request
        exc: The exception

    Returns:
        JSONResponse or TemplateResponse: A JSON response if the client
            prefers JSON, otherwise an HTML response rendered from a
            template
    """
    status_code = getattr(exc, "status_code", 500) or 500
    detail = getattr(exc, "detail", None)
    headers = getattr(exc, "headers", None)

    error = DEFAULT_ERRORS.get(status_code)
    if not error:
        error = ErrorTemplate(
            "Unexpected error",
            detail or "Something went wrong.",
            "Please try again later.",
        )

    if prefers_json(request):
        return build_json_response(
            status_code,
            "http",
            headers=headers,
            title=error.title,
            message=error.message,
            hint=error.hint,
        )

    return build_html_response(request, status_code, error, headers=headers)


async def validation_exception_handler(request: Request, exc: Exception):
    """Handle request validation errors and return appropriate responses
    based on client preferences.

    Args:
        request: The incoming HTTP request
        exc: The validation error

    Returns:
        JSONResponse or TemplateResponse: A JSON response if the client
            prefers JSON, otherwise an HTML response rendered from a
            template
    """
    errors = exc.errors() if isinstance(exc, RequestValidationError) else str(exc)

    if prefers_json(request):
        return build_json_response(
            422, "validation", message="Validation error", details=errors
        )

    return build_html_response(
        request,
        422,
        ErrorTemplate(
            "Validation error",
            "Some inputs were not valid.",
            "Please check the form and try again.",
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions and return appropriate responses
    based on client preferences.

    Args:
        request: The incoming HTTP request
        exc: The exception

    Returns:
        JSONResponse or TemplateResponse: A JSON response if the client
            prefers JSON, otherwise an HTML response rendered from a
            template
    """
    if prefers_json(request):
        return build_json_response(
            500, "server", message="Unexpected server error. Please try again later."
        )

    return build_html_response(
        request,
        500,
        ErrorTemplate(
            "Server error",
            "Unexpected server error. Please try again later.",
            "If the problem persists, contact support.",
        ),
    )
