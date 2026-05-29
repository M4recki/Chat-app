from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from uvicorn import run
from pathlib import Path
from datetime import datetime
from json import dumps, loads
from .routes import router
from .settings import settings
from .database import session_scope
from .models import Message
from .connection_manager import ConnectionManager
from .rate_limit import enforce_rate_limit
from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous.exc import SignatureExpired, BadSignature

app = FastAPI()

templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
)

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent.parent / "static"),
    name="static",
)

manager = ConnectionManager()

RATE_LIMIT_RULES = [
    {
        "path": "/login",
        "methods": {"POST"},
        "scope": "login",
        "max_requests": settings.rate_limit_login_max_requests,
        "window_seconds": settings.rate_limit_login_window_seconds,
    },
    {
        "path": "/chatbot",
        "methods": {"POST"},
        "scope": "chatbot",
        "max_requests": settings.rate_limit_chatbot_max_requests,
        "window_seconds": settings.rate_limit_chatbot_window_seconds,
    },
    {
        "path": "/search_user",
        "methods": {"GET"},
        "scope": "search_user",
        "max_requests": settings.rate_limit_search_max_requests,
        "window_seconds": settings.rate_limit_search_window_seconds,
    },
]


def get_rate_limit_identifier(request: Request) -> str | None:
    """Resolve the best-effort identifier for rate limiting.

    For authenticated users, returns 'user:{user_id}'. For unauthenticated requests, falls back to client IP address or 'unknown'.

    Args:
        request (Request): The incoming HTTP request
    Returns:            
        str | None: The resolved identifier for rate limiting, or None if it cannot be determined"""

    token = request.cookies.get("access_token")
    if not token:
        return None

    s = Serializer(settings.chat_secret_key)
    try:
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")
    except (SignatureExpired, BadSignature):
        return None

    if user_id is None:
        return None

    return f"user:{user_id}"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Middleware to enforce rate limits on incoming HTTP requests based on predefined rules.
    
    Checks the request path and method against defined rate limit rules, resolves an identifier for the client (user ID or IP), and enforces the limit using the RateLimiter. Adds rate limit metadata to response headers when applicable.

    Args:
        request (Request): The incoming HTTP request
        call_next: The next middleware or route handler to call
    Returns:
        Response: The HTTP response
    """
    path = request.url.path
    method = request.method.upper()
    identifier = get_rate_limit_identifier(request)
    rate_limit_meta = None

    try:
        for rule in RATE_LIMIT_RULES:
            if path == rule["path"] and method in rule["methods"]:
                rate_limit_meta = enforce_rate_limit(
                    request,
                    rule["scope"],
                    rule["max_requests"],
                    rule["window_seconds"],
                    identifier=identifier,
                )
                break
    except HTTPException as exc:
        return await http_exception_handler(request, StarletteHTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=exc.headers,
        ))

    response = await call_next(request)

    if rate_limit_meta:
        response.headers["X-RateLimit-Limit"] = str(rate_limit_meta["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rate_limit_meta["remaining"])
        response.headers["X-RateLimit-Reset"] = str(rate_limit_meta["reset"])

    return response


def prefers_json(request: Request) -> bool:
    """Determine if the client prefers a JSON response based on headers.

    Checks the 'X-Requested-With' header for AJAX requests and the 'Accept' header for JSON content types.

    Args:
        request (Request): The incoming HTTP request

    Returns:
        bool: True if the client prefers JSON, False otherwise"""
    requested_with = request.headers.get("X-Requested-With")
    if requested_with == "XMLHttpRequest":
        return True

    accept = request.headers.get("accept", "")
    return "application/json" in accept.lower()


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions and return appropriate responses based on client preferences.

    Args:
        request (Request): The incoming HTTP request
        exc (StarletteHTTPException): The exception

    Returns:
        JSONResponse or HTMLResponse: A JSON response if the client prefers JSON, otherwise an HTML response rendered from a template
    """
    status_code = exc.status_code or 500
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

    title, message, hint, show_login = default_messages.get(
        status_code,
        (
            "Unexpected error",
            exc.detail or "Something went wrong.",
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors and return appropriate responses based on client preferences.

    Args:
        request (Request): The incoming HTTP request
        exc (RequestValidationError): The validation error

    Returns:
        JSONResponse or HTMLResponse: A JSON response if the client prefers JSON, otherwise an HTML response rendered from a template
    """
    if prefers_json(request):
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation",
                "status_code": 422,
                "message": "Validation error",
                "details": exc.errors(),
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions and return appropriate responses based on client preferences.

    Args:
        request (Request): The incoming HTTP request
        exc (Exception): The exception

    Returns:
        JSONResponse or HTMLResponse: A JSON response if the client prefers JSON, otherwise an HTML response rendered from a template
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


@app.websocket("/ws/{channel_id}/{user_name}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket, channel_id: str, user_name: str, user_id: int
):
    """
    Handle incoming websocket connections.

    Accepts the websocket connection and broadcasts received messages
    to other clients in the channel. Saves messages to the database.

    Args:
        websocket (WebSocket): The websocket connection
        channel_id (str): The ID of the chat channel
        user_name (str): The name of the connected user
        user_id (int): The ID of the connected user

    Raises:
        WebSocketDisconnect: If the connection is closed
    """
    await manager.connect(websocket, channel_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = loads(data)
            channel_id = message_data["channel_id"]
            message = message_data["message"]

            # Create a message object in JSON format
            message_object = {
                "userId": user_id,
                "senderName": user_name,
                "content": message,
            }

            await manager.broadcast(dumps(message_object), channel_id)

            with session_scope() as db:
                new_message = Message(
                    content=message,
                    channel_id=channel_id,
                    created_at=datetime.now(),
                    user_id=user_id,
                )
                db.add(new_message)
                db.commit()

    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id)
        await manager.broadcast(
            dumps({"type": "system", "content": f"{user_name} left the chat"}),
            channel_id,
        )


app.include_router(router)

if __name__ == "__main__":
    run("python.main:app", reload=True)
