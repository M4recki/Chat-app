import logging
from os import environ
from textwrap import dedent

from datetime import datetime

from fastapi.responses import JSONResponse
from openai import OpenAI

from .settings import settings


class ChatbotServiceError(RuntimeError):
    def __init__(self, message: str, details=None):
        super().__init__(message)
        self.details = details or {}


def normalize_chatbot_response(response_text: str):
    """Normalize the chatbot response by stripping whitespace and dedenting.

    Args:
        response_text (str): The raw response text from the chatbot

    Returns:
        str: The normalized response text
    """
    if not response_text:
        return ""
    return dedent(response_text).strip()


def build_chatbot_messages(user_input: str, previous_messages=None):
    """
    Build the message history for the chatbot API request.

    Args:
        user_input (str): The current user input message
        previous_messages (list, optional): A list of previous messages

    Returns:
        list: The list of messages for the chatbot API request
    """
    system_prompt = (
        "You are the Chat App assistant. "
        "Use the provided conversation history as memory for this user. "
        "If the user asks whether you remember earlier messages, answer based on the "
        "history in this chat context. "
        "Do not claim you cannot remember previous messages when prior context is present. "
        "Answer completely and avoid trailing fragments or unfinished Markdown. "
        "For factual or cost-related questions, give a concise estimate, key factors, and a brief caveat."
    )

    messages = [{"role": "system", "content": system_prompt}]
    if previous_messages:
        for item in previous_messages:
            if item.message:
                messages.append({"role": "user", "content": item.message})
            if item.response:
                messages.append({"role": "assistant", "content": item.response})

    messages.append({"role": "user", "content": user_input})
    return messages


def chatbot_response(user_input: str, previous_messages=None):
    """
    Get a response from the chatbot for the given user input.

    Args:
        user_input (str): The user's message
        previous_messages (list, optional): Prior chatbot messages for context

    Returns:
        str: The chatbot's response
    """
    if environ.get("TESTING") == "1":
        if ":" in user_input:
            return user_input.split(":", 1)[1].strip()
        return "test-response"

    api_key = settings.ai_key.strip().strip('"').strip("'")
    if api_key.lower().startswith("bearer "):
        api_key = api_key.split(" ", 1)[1].strip()
    if not api_key or api_key.lower() in {"your-nvidia-api-key", "changeme"}:
        raise ChatbotServiceError(
            "Chatbot service is not configured",
            {"reason": "Missing or placeholder AI_KEY"},
        )

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
        timeout=settings.chatbot_timeout_seconds,
        max_retries=settings.chatbot_max_retries,
    )
    messages = build_chatbot_messages(user_input, previous_messages)

    model_errors = []
    for model_name in settings.chatbot_models:
        try:
            try:
                completion = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.6,
                    top_p=0.9,
                    max_tokens=settings.chatbot_max_tokens,
                    stream=False,
                )
            except Exception as exc_inner:
                if hasattr(openai, "APITimeoutError") and isinstance(
                    exc_inner, openai.APITimeoutError
                ):
                    logging.warning(
                        "Chatbot model %s timed out; retrying with longer timeout and fewer tokens",
                        model_name,
                    )
                    try:
                        retry_max_tokens = max(
                            256, int(settings.chatbot_max_tokens / 2)
                        )
                        completion = client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            temperature=0.6,
                            top_p=0.9,
                            max_tokens=retry_max_tokens,
                            stream=False,
                            timeout=min(
                                getattr(settings, "chatbot_timeout_seconds", 30) * 2,
                                300,
                            ),
                        )
                    except Exception as exc_retry:
                        raise exc_retry
                else:
                    raise exc_inner

            message = completion.choices[0].message
            content = message.content if message else None
            if content:
                return normalize_chatbot_response(content)
            model_errors.append(f"Model {model_name} returned an empty response")
        except Exception as exc:
            model_errors.append(f"Model {model_name} failed: {exc}")
            if getattr(settings, "debug", False):
                logging.getLogger("chatbot").exception(
                    "Chatbot model %s failed", model_name
                )

    raise ChatbotServiceError(
        "Chatbot service is temporarily unavailable",
        {"models": list(settings.chatbot_models), "attempts": model_errors},
    )


def chatbot_context(user, chatbot_messages, **extra):
    """
    Build the context for rendering chatbot templates.

    Args:
        user (User): The current user
        chatbot_messages (list): List of previous chatbot messages
        extra: Additional context variables

    Returns:
        dict: The context for template rendering"""
    context = {
        "request": extra.pop("request"),
        "user": user,
        "message": extra.pop("message", ""),
        "response": extra.pop("response", ""),
        "chatbot_messages": chatbot_messages,
    }
    context.update(extra)
    return context


def chatbot_json_error(status_code: int, payload: dict):
    """Return a structured JSON error response for chatbot API errors.

    Args:
        status_code (int): The HTTP status code for the error response
        payload (dict): A dictionary containing error details

    Returns:
        JSONResponse: A FastAPI JSONResponse with the error details
    """
    return JSONResponse(status_code=status_code, content=payload)


def chatbot_json_success(message: str, response: str, created_at: datetime):
    """Return a structured JSON success response for chatbot API responses.

    Args:
        message (str): The success message
        response (str): The chatbot's response
        created_at (datetime): The timestamp for when the response was created

    Returns:
        JSONResponse: A FastAPI JSONResponse with the success details
    """
    return JSONResponse(
        status_code=200,
        content={
            "message": message,
            "response": response,
            "created_at": created_at.strftime(" %H:%M, %Y-%m-%d"),
        },
    )
