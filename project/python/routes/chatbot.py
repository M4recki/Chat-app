import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request

from ..chatbot_utils import (ChatbotServiceError, chatbot_context,
                             chatbot_json_error, chatbot_json_success,
                             chatbot_response)
from ..database import session_scope
from ..models import ChatbotMessage, User
from ..settings import settings
from .helpers import get_current_user, validate_csrf
from .template import encode_avatar, templates

router = APIRouter()


@router.get("/chatbot")
async def chatbot_page(request: Request, user: User = Depends(get_current_user)):
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

    with session_scope() as db:
        chatbot_messages = (
            db.query(ChatbotMessage)
            .filter(ChatbotMessage.user_id == user.id)
            .all()
        )

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


@router.post("/chatbot", dependencies=[Depends(validate_csrf)])
async def chatbot(request: Request, message: str = Form(...), user: User = Depends(get_current_user)):
    """
    Send a new message to the chatbot.

    Saves the user message and chatbot response to the database.

    Args:
        request (Request): The HTTP request
        message (str): The user's message
        user: The authenticated user

    Returns:
        TemplateResponse: The chatbot chat page
    """

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    errors = {}
    if len(message) <= 0:
        errors["message"] = "Message cannot be empty"

    if errors:
        if is_ajax:
            return chatbot_json_error(
                400, {"error": "validation", "details": errors}
            )
        return templates.TemplateResponse(
            request,
            "chatbot_chat.html",
            chatbot_context(
                user, [], request=request, message=message,
                errors=errors,
            ),
        )

    history_limit = max(0, settings.chatbot_history_limit)
    with session_scope() as db:
        recent_history = (
            db.query(ChatbotMessage)
            .filter(ChatbotMessage.user_id == user.id)
            .order_by(ChatbotMessage.created_at.desc())
            .limit(history_limit)
            .all()
        )
        recent_history.reverse()

    try:
        response = chatbot_response(message, previous_messages=recent_history)
    except ChatbotServiceError as exc:
        logging.warning("Chatbot request failed: %s", exc)
        error_payload = {
            "error": "chatbot",
            "message": str(exc),
            "error_type": exc.__class__.__name__,
            "details": exc.details,
        }
        if is_ajax:
            return chatbot_json_error(502, error_payload)
        return templates.TemplateResponse(
            request,
            "chatbot_chat.html",
            chatbot_context(
                user,
                [],
                request=request,
                message=message,
                errors=error_payload,
            ),
        )
    except Exception as exc:
        logging.exception("Chatbot request failed")
        error_payload = {
            "error": "chatbot",
            "message": "Chatbot service failed. Check server logs.",
            "error_type": exc.__class__.__name__,
        }
        if is_ajax:
            return chatbot_json_error(502, error_payload)
        return templates.TemplateResponse(
            request,
            "chatbot_chat.html",
            chatbot_context(
                user,
                [],
                request=request,
                message=message,
                errors=error_payload,
            ),
        )

    created_at = datetime.now()
    chatbot_message = ChatbotMessage(
        user_id=user.id,
        message=message,
        response=response,
        created_at=created_at,
    )
    with session_scope() as db:
        db.add(chatbot_message)
        db.commit()

    if is_ajax:
        return chatbot_json_success(message, response, created_at)

    with session_scope() as db:
        chatbot_messages = (
            db.query(ChatbotMessage)
            .filter(ChatbotMessage.user_id == user.id)
            .all()
        )

    return templates.TemplateResponse(
        request,
        "chatbot_chat.html",
        chatbot_context(
            user,
            chatbot_messages,
            request=request,
            message=message,
            response=response,
        ),
    )


# Clear past conversations with chatbot


@router.post("/clear_chatbot_messages", dependencies=[Depends(validate_csrf)])
async def clear_chatbot_messages(request: Request, user: User = Depends(get_current_user)):
    """
    Clear all past chatbot messages for the user.

    Args:
        request (Request): The HTTP request
        user: The authenticated user

    Returns:
        TemplateResponse: The chatbot chat page
    """
    with session_scope() as db:
        (
            db.query(ChatbotMessage)
            .filter(ChatbotMessage.user_id == user.id)
            .delete()
        )
        db.commit()

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
