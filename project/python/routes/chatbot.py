import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy import select

from ..chatbot_utils import (
    ChatbotServiceError,
    chatbot_context,
    chatbot_json_error,
    chatbot_json_success,
    chatbot_response,
)
from ..database import async_session_scope
from ..models import ChatbotMessage, User
from ..settings import settings
from .helpers import get_current_user, validate_csrf
from .template import encode_avatar, templates

router = APIRouter()


@router.get("/chatbot")
async def chatbot_page(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """
    Render the chatbot chat page.

    Retrieves the logged-in user and their past chatbot messages.

    Args:
        request (Request): The HTTP request
        user: The authenticated user

    Returns:
        TemplateResponse: The chatbot chat page
    """
    user.avatar = encode_avatar(user)

    async with async_session_scope() as db:
        result = await db.execute(
            select(ChatbotMessage).filter(ChatbotMessage.user_id == user.id)
        )
        chatbot_messages = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "chatbot_chat.html",
        {
            "request": request,
            "user": user,
            "user_image": user.avatar,
            "chatbot_messages": chatbot_messages,
        },
    )


# Handle chatbot message submission


def handle_chatbot_error(
    request: Request,
    user: User,
    message: str,
    is_ajax: bool,
    error_payload: dict,
) -> Response:
    """Handle a chatbot error by returning JSON or HTML as appropriate.

    Args:
        request: The request object
        user: The authenticated user
        message: The original user message
        is_ajax: Whether the request expects JSON
        error_payload: The error details to include in the response

    Returns:
        Response: JSON or HTML error response
    """
    if is_ajax:
        return chatbot_json_error(502, error_payload)
    return templates.TemplateResponse(
        request,
        "chatbot_chat.html",
        chatbot_context(
            user, [], request=request, message=message, errors=error_payload
        ),
    )


@router.post("/chatbot", dependencies=[Depends(validate_csrf)])
async def chatbot(
    request: Request,
    message: str = Form(...),
    user: User = Depends(get_current_user),
) -> Response:
    """Send a new message to the chatbot.

    Args:
        request: The request object
        message: The user's message text
        user: The authenticated user

    Returns:
        Response: JSON or HTML response with the chatbot reply
    """
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if len(message) <= 0:
        if is_ajax:
            return chatbot_json_error(
                400,
                {
                    "error": "validation",
                    "details": {"message": "Message cannot be empty"},
                },
            )
        return templates.TemplateResponse(
            request,
            "chatbot_chat.html",
            chatbot_context(
                user,
                [],
                request=request,
                message=message,
                errors={"message": "Message cannot be empty"},
            ),
        )

    history_limit = max(0, settings.chatbot_history_limit)
    async with async_session_scope() as db:
        result = await db.execute(
            select(ChatbotMessage)
            .filter(ChatbotMessage.user_id == user.id)
            .order_by(ChatbotMessage.created_at.desc())
            .limit(history_limit)
        )
        recent_history = result.scalars().all()
        recent_history.reverse()

    try:
        response = chatbot_response(message, previous_messages=recent_history)
    except ChatbotServiceError as exc:
        logging.warning("Chatbot request failed: %s", exc)
        return handle_chatbot_error(
            request,
            user,
            message,
            is_ajax,
            {
                "error": "chatbot",
                "message": str(exc),
                "error_type": exc.__class__.__name__,
                "details": exc.details,
            },
        )
    except Exception as exc:
        logging.exception("Chatbot request failed")
        return handle_chatbot_error(
            request,
            user,
            message,
            is_ajax,
            {
                "error": "chatbot",
                "message": "Chatbot service failed. Check server logs.",
                "error_type": exc.__class__.__name__,
            },
        )

    created_at = datetime.now()
    async with async_session_scope() as db:
        db.add(
            ChatbotMessage(
                user_id=user.id,
                message=message,
                response=response,
                created_at=created_at,
            )
        )

    if is_ajax:
        return chatbot_json_success(message, response, created_at)

    async with async_session_scope() as db:
        result = await db.execute(
            select(ChatbotMessage).filter(ChatbotMessage.user_id == user.id)
        )
        chatbot_messages = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "chatbot_chat.html",
        chatbot_context(
            user, chatbot_messages, request=request, message=message, response=response
        ),
    )


# Clear past conversations with chatbot


@router.post("/clear_chatbot_messages", dependencies=[Depends(validate_csrf)])
async def clear_chatbot_messages(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """
    Clear all past chatbot messages for the user.

    Args:
        request (Request): The HTTP request
        user: The authenticated user

    Returns:
        TemplateResponse: The chatbot chat page
    """
    async with async_session_scope() as db:
        result = await db.execute(
            select(ChatbotMessage).filter(ChatbotMessage.user_id == user.id)
        )
        for msg in result.scalars().all():
            await db.delete(msg)

    return templates.TemplateResponse(
        request,
        "chatbot_chat.html",
        chatbot_context(
            user,
            [],
            request=request,
            user_image=encode_avatar(user),
        ),
    )
