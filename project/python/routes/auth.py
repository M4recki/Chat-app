from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from itsdangerous import URLSafeTimedSerializer as Serializer
from PIL import Image
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from ..database import async_session_scope
from ..models import User
from ..settings import settings
from .email import (
    generate_password_reset_token,
    send_reset_email,
    verify_password_reset_token,
)
from .helpers import is_authenticated, validate_csrf_optional, validate_email
from .template import DEFAULT_AVATAR_PATH, render_template

router = APIRouter()


def set_auth_cookie(response: Response, user_id: int) -> None:
    """Set the authentication cookie on the response.

    Args:
        response: The HTTP response to attach the cookie to
        user_id: The user ID to encode in the token
    """
    s = Serializer(settings.chat_secret_key)
    token = s.dumps({"user_id": user_id})
    response.set_cookie(
        key=settings.access_token_cookie,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )


@router.get("/sign_up", name="sign_up")
def sign_up_page(request: Request):
    """Render the sign-up page.

    Args:
        request: The request object

    Returns:
        Response: Sign up page template response
    """
    return render_template("sign_up.html", request, errors={})


@router.post("/sign_up", dependencies=[Depends(validate_csrf_optional)])
async def sign_up_data(
    request: Request,
    name: str = Form(...),
    surname: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    terms_conditions: bool = Form(...),
) -> Response:
    """Handle sign up form submission.

    Args:
        request: The request object
        name: The name form field
        surname: The surname form field
        email: The email form field
        password: The password form field
        confirm_password: The confirm password form field
        terms_conditions: The terms and conditions form field

    Returns:
        Response: Redirect to home or sign up template
    """
    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.email == email))
        existing = result.scalar()

        errors = {}
        if not validate_email(email):
            errors["email"] = "Invalid email format"
        if existing and "email" not in errors:
            errors["email"] = "User with this email already exists"
        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters long"
        if password != confirm_password:
            errors["confirm_password"] = "Passwords do not match"

        if errors:
            return render_template("sign_up.html", request, errors=errors)

        img_binary = BytesIO()
        with Image.open(DEFAULT_AVATAR_PATH) as img:
            img.save(img_binary, format="PNG")

        new_user = User(
            name=name,
            surname=surname,
            email=email,
            password=generate_password_hash(password),
            avatar=img_binary.getvalue(),
            created_at=datetime.now(),
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

    response = RedirectResponse(request.url_for("single_chat"), status_code=303)
    set_auth_cookie(response, new_user.id)
    return response


# Login


@router.get("/login", name="login")
def login_page(request: Request):
    """Render the login page.

    Args:
        request: The request object

    Returns:
        Response: Login page template response
    """
    return render_template("login.html", request)


@router.post("/login", dependencies=[Depends(validate_csrf_optional)])
async def login_data(
    request: Request, email: str = Form(...), password: str = Form(...)
) -> Response:
    """Handle login form submission.

    Args:
        request: The request object
        email: The email form field
        password: The password form field

    Returns:
        Response: Redirect or login template on validation errors
    """
    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalar()

        if not user or not check_password_hash(user.password, password):
            return render_template(
                "login.html", request, errors={"login": "Invalid email or password"}
            )

    response = RedirectResponse(request.url_for("single_chat"), status_code=303)
    set_auth_cookie(response, user.id)
    return response


@router.get("/logout", dependencies=[Depends(is_authenticated)])
def logout(request: Request) -> Response:
    """Logout the currently authenticated user.

    Args:
        request: The request object

    Returns:
        Response: Redirect to log in or home page
    """
    token = request.cookies.get(settings.access_token_cookie)
    if token:
        response = RedirectResponse(request.url_for("root"), status_code=303)
        response.delete_cookie(key=settings.access_token_cookie)
        return response
    else:
        return render_template("login.html", request)


@router.get("/forgot_password", name="forgot_password")
def forgot_password_page(request: Request) -> Response:
    """Render the forgot password page.

    Args:
        request: The request object

    Returns:
        Response: Forgot password page template response
    """
    return render_template("forgot_password.html", request, errors={})


@router.post("/forgot_password", dependencies=[Depends(validate_csrf_optional)])
async def forgot_password_data(request: Request, email: str = Form(...)) -> Response:
    """Handle forgot password form submission.

    Always returns the same success message regardless of whether
    the email exists, to avoid revealing registered addresses.

    Args:
        request: The request object
        email: The email form field

    Returns:
        Response: Forgot password template response with success message
    """
    errors = {}

    if not validate_email(email):
        errors["email"] = "Invalid email format"
        return render_template("forgot_password.html", request, errors=errors)

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalar()

    if user:
        token = generate_password_reset_token(email)
        reset_link = str(request.url_for("reset_password", token=token))
        send_reset_email(email, reset_link)

    return render_template(
        "forgot_password.html",
        request,
        success="If an account with that email exists, we have sent a password reset link.",
    )


@router.get("/reset_password/{token}", name="reset_password")
def reset_password_page(request: Request, token: str) -> Response:
    """Render the reset password page.

    Validates the token and shows the password form if valid.

    Args:
        request: The request object
        token: The signed password reset token

    Returns:
        Response: Reset password template response
    """
    email = verify_password_reset_token(token)
    errors = {}
    if email is None:
        errors["token"] = (
            "This reset link is invalid or has expired. " "Please request a new one."
        )
    return render_template("reset_password.html", request, token=token, errors=errors)


@router.post(
    "/reset_password/{token}",
    dependencies=[Depends(validate_csrf_optional)],
)
async def reset_password_data(
    request: Request,
    token: str,
    password: str = Form(...),
    confirm_password: str = Form(...),
) -> Response:
    """Handle reset password form submission.

    Validates the token and updates the user's password.

    Args:
        request: The request object
        token: The signed password reset token
        password: The new password form field
        confirm_password: The confirm password form field

    Returns:
        Response: Reset password template response
    """
    email = verify_password_reset_token(token)
    errors = {}

    if email is None:
        errors["token"] = (
            "This reset link is invalid or has expired. " "Please request a new one."
        )
        return render_template(
            "reset_password.html", request, token=token, errors=errors
        )

    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters long"

    if password != confirm_password:
        errors["confirm_password"] = "Passwords do not match"

    if errors:
        return render_template(
            "reset_password.html", request, token=token, errors=errors
        )

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalar()
        if user:
            user.password = generate_password_hash(password)
            await db.commit()

    return render_template(
        "reset_password.html",
        request,
        token=token,
        errors={},
        success="Your password has been reset successfully. You can now log in.",
    )
