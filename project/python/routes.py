from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer as Serializer
from pathlib import Path
from datetime import datetime, timedelta
from email.message import EmailMessage
from ssl import create_default_context
import smtplib
from os import environ
from PIL import Image
from io import BytesIO
from base64 import b64encode
from gpt4all import GPT4All
from database import SessionLocal
from models import User, Friend, Group, GroupUser, ChatbotMessage


router = APIRouter()


# Authentication


def is_authenticated(request: Request):
    token = request.cookies.get("access_token")
    if token:
        return {"is_authenticated": True}
    else:
        return {"is_authenticated": False}


def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        try:
            user_id = s.loads(token, max_age=3600).get("user_id")
            db = SessionLocal()
            user = db.query(User).filter(User.id == user_id).first()
            return user
        except:
            return templates.TemplateResponse("login.html", {"request": request})

    else:
        return templates.TemplateResponse("login.html", {"request": request})


# User image


def user_image(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        try:
            user_id = s.loads(token, max_age=3600).get("user_id")
            db = SessionLocal()
            user = db.query(User).filter(User.id == user_id).first()
            return {"user_image": b64encode(user.avatar).decode("utf-8")}
        except:
            return {"user_image": None}
    else:
        return {"user_image": None}


# User name


def user_name(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        try:
            user_id = s.loads(token, max_age=3600).get("user_id")
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
    context_processors=[current_year, is_authenticated, user_image, user_name],
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
    img_binary = BytesIO()
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

    elif not check_password_hash(user.password, password):
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

    context = create_default_context()

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


@router.get("/logout", dependencies=[Depends(get_current_user)])
def logout(request: Request):
    response = RedirectResponse(request.url_for("root"), status_code=303)
    response.delete_cookie(key="access_token")
    return response


# Search user


@router.get("/search_user", dependencies=[Depends(get_current_user)])
async def search_user(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        users = db.query(User).filter(User.id != user_id).all()
        for user in users:
            user.avatar = b64encode(user.avatar).decode()
        return templates.TemplateResponse(
            "search_user.html", {"request": request, "users": users}
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Friend requests


@router.get("/friend_requests", dependencies=[Depends(get_current_user)])
async def friend_requests(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        friend_requests = (
            db.query(Friend)
            .filter(Friend.user2_id == user_id, Friend.status == "pending")
            .all()
        )
        for friend_request in friend_requests:
            friend_request.user1.avatar = b64encode(
                friend_request.user1.avatar
            ).decode()
        return templates.TemplateResponse(
            "friend_requests.html",
            {"request": request, "friend_requests": friend_requests},
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Single chat


@router.get("/single_chat", dependencies=[Depends(get_current_user)])
async def single_chat(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        users = (
            db.query(User)
            .join(Friend, (Friend.user1_id == User.id) | (Friend.user2_id == User.id))
            .filter(
                (Friend.user1_id == user_id) | (Friend.user2_id == user_id),
                Friend.status == "accepted",
            )
            .all()
        )
        for user in users:
            user.avatar = b64encode(user.avatar).decode()
        return templates.TemplateResponse(
            "single_chat.html", {"request": request, "users": users}
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Group chat


@router.get("/group_chat", dependencies=[Depends(get_current_user)])
async def group_chat(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        groups = (
            db.query(Group)
            .join(GroupUser, GroupUser.group_id == Group.id)
            .filter(GroupUser.user_id == user_id)
            .all()
        )
        for group in groups:
            group.avatar = b64encode(group.avatar).decode()
        return templates.TemplateResponse(
            "group_chat.html", {"request": request, "groups": groups}
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Create group


@router.get("/create_group", dependencies=[Depends(get_current_user)])
async def create_group(request: Request):
    return templates.TemplateResponse("create_group.html", {"request": request})


# Add friend


@router.get("/add_friend/{friend_id}", dependencies=[Depends(get_current_user)])
async def add_friend(request: Request, friend_id: int):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        existing_request = (
            db.query(Friend)
            .filter((Friend.user1_id == user_id) & (Friend.user2_id == friend_id))
            .first()
        )

        if existing_request and existing_request.status == "pending":
            if datetime.now() - existing_request.last_sent > timedelta(days=14):
                existing_request.last_sent = datetime.now()
                db.commit()
            else:
                raise HTTPException(
                    status_code=400, detail="Friend request already sent recently"
                )
        elif existing_request and existing_request.status == "denied":
            existing_request.status = "pending"
            existing_request.last_sent = datetime.now()
            db.commit()
        else:
            new_friendship = Friend(
                user1_id=user_id,
                user2_id=friend_id,
                status="pending",
                last_sent=datetime.now(),
            )
            db.add(new_friendship)
            db.commit()

        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Accept friend requests


@router.post("/accept_friend/{friend_id}", dependencies=[Depends(get_current_user)])
async def accept_friend(request: Request, friend_id: int):
    db = SessionLocal()
    user_id = request.cookies.get("access_token")
    friend = (
        db.query(Friend)
        .filter(Friend.user1_id == friend_id, Friend.user2_id == user_id)
        .first()
    )
    friend.status = "accepted"
    db.commit()
    return templates.TemplateResponse("single_chat.html", {"request": request})


# Deny friend requests


@router.post("/deny_friend/{friend_id}", dependencies=[Depends(get_current_user)])
async def deny_friend(request: Request, friend_id: int):
    db = SessionLocal()
    user_id = request.cookies.get("access_token")
    friend = (
        db.query(Friend)
        .filter(Friend.user1_id == friend_id, Friend.user2_id == user_id)
        .first()
    )
    friend.status = "denied"
    db.commit()
    return templates.TemplateResponse("single_chat.html", {"request": request})


# Ai chat


def chatbot_response(user_input: str):
    model = GPT4All(model_name="gpt4all-falcon-q4_0.gguf")

    with model.chat_session():
        response = model.generate(prompt=f"{user_input}", temp=0)
        return model.current_chat_session[2]["content"]


@router.get("/chatbot", dependencies=[Depends(get_current_user)])
async def chatbot_page(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        user = db.query(User).filter(User.id == user_id).first()
        
        return templates.TemplateResponse(
            "chatbot.html", {"request": request, "user": user}
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


@router.post("/chatbot", dependencies=[Depends(get_current_user)])
async def chatbot(request: Request, message: str = Form(...)):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        
        user = db.query(User).filter(User.id == user_id).first()
        
        response = chatbot_response(message)
    
        chatbot_message = ChatbotMessage(
            user_id=user.id, message=message, response=response,
            created_at=datetime.now()
        )
        db.add(chatbot_message)
        db.commit()

        return templates.TemplateResponse(
            "chatbot.html", {"request": request, "user": user, "user_image": user.avatar, "message": message, "response": response}
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


@router.get("/chatbot_messages", dependencies=[Depends(get_current_user)])
async def chatbot_messages(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        
        user = db.query(User).filter(User.id == user_id).first()
        chatbot_messages = (
            db.query(ChatbotMessage).filter(ChatbotMessage.user_id == user.id).all()
        )
        return templates.TemplateResponse(
            "chatbot_messages.html",
            {"request": request, "chatbot_messages": chatbot_messages},
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})
