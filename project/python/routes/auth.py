from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from itsdangerous import URLSafeTimedSerializer as Serializer
from PIL import Image
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from ..database import async_session_scope
from ..models import User
from ..settings import settings
from .helpers import is_authenticated, validate_csrf_optional, validate_email
from .template import DEFAULT_AVATAR_PATH, render_template

router = APIRouter()


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
        user = result.scalar()

        errors = {}

        if not validate_email(email):
            errors["email"] = "Invalid email format"

        if user and "email" not in errors:
            errors["email"] = "User with this email already exists"

        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters long"

        if password != confirm_password:
            errors["confirm_password"] = "Passwords do not match"

        if errors:
            return render_template("sign_up.html", request, errors=errors)

        hashed_password = generate_password_hash(password)

        img_binary = BytesIO()
        with Image.open(DEFAULT_AVATAR_PATH) as img:
            img.save(img_binary, format="PNG")
        avatar_bytes = img_binary.getvalue()

        new_user = User(
            name=name,
            surname=surname,
            email=email,
            password=hashed_password,
            avatar=avatar_bytes,
            created_at=datetime.now(),
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

    s = Serializer(settings.chat_secret_key)
    token = s.dumps({"user_id": new_user.id})

    response = RedirectResponse(request.url_for("single_chat"), status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )

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
    from werkzeug.security import check_password_hash

    async with async_session_scope() as db:
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalar()

        errors = {}

        if not user:
            errors["email"] = "User with this email does not exist"

        elif not check_password_hash(user.password, password):
            errors["password"] = "Incorrect password. Please try again"

        if errors:
            return render_template("login.html", request, errors=errors)

        s = Serializer(settings.chat_secret_key)
        token = s.dumps({"user_id": user.id})

    response = RedirectResponse(request.url_for("single_chat"), status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )

    return response


@router.get("/logout", dependencies=[Depends(is_authenticated)])
def logout(request: Request) -> Response:
    """Logout the currently authenticated user.

    Args:
        request: The request object

    Returns:
        Response: Redirect to log in or home page
    """
    token = request.cookies.get("access_token")
    if token:
        response = RedirectResponse(request.url_for("root"), status_code=303)
        response.delete_cookie(key="access_token")
        return response
    else:
        return render_template("login.html", request)
