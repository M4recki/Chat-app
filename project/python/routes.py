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
from models import User


router = APIRouter()


def current_year(request: Request):
    return {"current_year": datetime.now().year}


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
    context_processors=[current_year],
)

# Main page


@router.get("/")
def root(request: Request):
    return templates.TemplateResponse("main_page.html", {"request": request})


# Sign up


@router.get("/sign_up", name="sign_up")
def sign_up_page(request: Request):
    return templates.TemplateResponse("sign_up.html", {"request": request})


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

    if user:
        return templates.TemplateResponse(
            "sign_up.html",
            {"request": request, "error": "User with this email already exists"},
        )

    if len(email) < 8:
        return templates.TemplateResponse(
            "sign_up.html",
            {
                "request": request,
                "error": "Password must be at least 8 characters long",
            },
        )

    if not terms_conditions:
        return templates.TemplateResponse(
            "sign_up.html",
            {"request": request, "error": "You must accept the terms and conditions"},
        )

    if email.find("@") == -1:
        return templates.TemplateResponse(
            "sign_up.html", {"request": request, "error": "Invalid email"}
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            "sign_up.html", {"request": request, "error": "Passwords do not match"}
        )

    hashed_password = generate_password_hash(
        password, method="pbkdf2:sha256", salt_length=6
    )
    new_user = User(
        name=name,
        surname=surname,
        email=email,
        password=hashed_password,
        created_at=datetime.now(),
    )
    db.add(new_user)
    db.commit()

    SECRET_KEY = environ.get("Secret_key_chat")
    s = Serializer(SECRET_KEY)
    token = s.dumps({"user_id": new_user.id}, expires_in=timedelta(hours=1))

    response = RedirectResponse(request.url_for("root"), status_code=303)
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

    if not user:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "User not found"}
        )

    if not check_password_hash(user.password, password):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Incorrect password"}
        )

    SECRET_KEY = environ.get("Secret_key_chat")
    s = Serializer(SECRET_KEY)
    token = s.dumps({"user_id": user.id}, expires_in=timedelta(hours=1))

    response = RedirectResponse(request.url_for("root"), status_code=303)
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
    send_email(email, subject, message)
    flash_messages = ["Your message has been sent"]
    return templates.TemplateResponse(
        "main_page.html", {"request": request, "flash_messages": flash_messages}
    )
