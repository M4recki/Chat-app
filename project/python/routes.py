from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer as Serializer
from pathlib import Path
from datetime import datetime, timedelta
from database import SessionLocal
from email.message import EmailMessage
import ssl
import smtplib
from os import environ
from PIL import Image
import io
from models import User


router = APIRouter()

# Authentication


def is_authenticated(request: Request):
    token = request.cookies.get("access_token")
    if token:
        return {"is_authenticated": True}
    else:
        return {"is_authenticated": False}


# User name


def user_name(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        try:
            user_id = s.loads(token, max_age=3600).get('user_id')
            db = SessionLocal()
            user = db.query(User).filter(User.id == user_id).first()
            return {"user_name": user.name}
        except:
            return {"user_name": None}
    else:
        return {"user_name": None}


# Current year in footer


def current_year(request: Request):
    return {"current_year": datetime.now().year}


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
    context_processors=[current_year, is_authenticated, user_name],
)

# Main page


@router.get("/")
def root(request: Request):
    return templates.TemplateResponse("main_page.html", {"request": request})


# Sign up


@router.get("/sign_up", name="sign_up")
def sign_up_page(request: Request):
    return templates.TemplateResponse(
        "sign_up.html", {"request": request, "errors": {}}
    )


@router.post("/sign_up")
async def sign_up_data(
    request: Request,
    name: str = Form(...),
    surname: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    terms_conditions: bool = Form(...),
):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()

    errors = {}

    if user:
        errors["email"] = "User with this email already exists"

    if not password.isalnum():
        errors["password"] = "Password must contain only letters and numbers"

    if password != confirm_password:
        errors["confirm_password"] = "Passwords do not match"

    if errors:
        return templates.TemplateResponse(
            "sign_up.html", {"request": request, "errors": errors}
        )

    hashed_password = generate_password_hash(
        password, method="pbkdf2:sha256", salt_length=6
    )

    img = Image.open("project/static/img/default avatar.jpg")
    img_binary = io.BytesIO()
    img.save(img_binary, format="JPEG")
    img_binary = img_binary.getvalue()

    new_user = User(
        name=name,
        surname=surname,
        email=email,
        password=hashed_password,
        avatar=img_binary,
        created_at=datetime.now(),
    )
    db.add(new_user)
    db.commit()

    SECRET_KEY = environ.get("Secret_key_chat")
    s = Serializer(SECRET_KEY)
    token = s.dumps({"user_id": new_user.id})

    response = RedirectResponse(request.url_for("single_chat"), status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True)

    return response


# Login


@router.get("/login", name="login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_data(
    request: Request, email: str = Form(...), password: str = Form(...)
):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()

    errors = {}

    if not user:
        errors["email"] = "User with this email does not exist"

    if not check_password_hash(user.password, password):
        errors["password"] = "Incorrect password. Please try again"

    if errors:
        return templates.TemplateResponse(
            "login.html", {"request": request, "errors": errors}
        )

    SECRET_KEY = environ.get("Secret_key_chat")
    s = Serializer(SECRET_KEY)
    token = s.dumps({"user_id": user.id})

    response = RedirectResponse(request.url_for("single_chat"), status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True)

    return response


# Contact


def send_email(email_address, subject, message):
    email_receiver = environ.get("EMAIL_RECEIVER_TODO")
    password = environ.get("EMAIL_PASSWORD_CAFE")

    email = EmailMessage()

    email["From"] = email_address
    email["To"] = email_receiver
    email["Subject"] = subject
    email.set_content(message)

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
        smtp.login(email_receiver, password)
        smtp.sendmail(email_address, email_receiver, email.as_string())


@router.get("/contact", name="contact")
def contact_page(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})


@router.post("/contact")
async def contact_data(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
):
    errors = {}

    if len(message) < 10:
        errors["message"] = "Message must contain at least 10 characters"

    send_email(email, subject, message)
    flash_messages = ["Your message has been sent"]
    return templates.TemplateResponse(
        "main_page.html", {"request": request, "flash_messages": flash_messages}
    )


# Logout


@router.get("/logout")
def logout(request: Request):
    response = RedirectResponse(request.url_for("root"), status_code=303)
    response.delete_cookie(key="access_token")
    return response


# Single chat


@router.get("/single_chat")
def single_chat(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        try:
            user_id = s.loads(token, max_age=3600).get('user_id')
            db = SessionLocal()
            user = db.query(User).filter(User.id == user_id).first()
            return templates.TemplateResponse(
                "single_chat.html", {"request": request, "user": user}
            )
        except:
            return templates.TemplateResponse("login.html", {"request": request})
    return templates.TemplateResponse("single_chat.html", {"request": request})


# Group chat


@router.get("/group_chat")
def group_chat(request: Request):
    return templates.TemplateResponse("group_chat.html", {"request": request})


# AI chat


@router.get("/ai_chat")
def ai_chat(request: Request):
    return templates.TemplateResponse("ai_chat.html", {"request": request})
