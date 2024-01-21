from fastapi import (
    APIRouter,
    Request,
    Form,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous.exc import SignatureExpired
from pathlib import Path
from datetime import datetime, timedelta
from email.message import EmailMessage
from ssl import create_default_context
import smtplib
from os import environ
from PIL import Image
from io import BytesIO
from base64 import b64encode
from uuid import uuid4
from gpt4all import GPT4All
from database import SessionLocal
from models import User, Friend, Group, GroupUser, ChatbotMessage, Message, Channel
from connection_manager import ConnectionManager


router = APIRouter()

manager = ConnectionManager()

# Authentication


def authentication_in_header(request: Request):
    token = request.cookies.get("access_token")
    if token:
        return {"is_authenticated": True}
    else:
        return {"is_authenticated": False}


def is_authenticated(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        try:
            user_id = s.loads(token, max_age=3600).get("user_id")
            db = SessionLocal()
            user = db.query(User).filter(User.id == user_id).first()
            return user
        except SignatureExpired:
            response = RedirectResponse(request.url_for("root"), status_code=303)
            response.delete_cookie(key="access_token")
            return templates.TemplateResponse(
                "login.html", {"request": request, "response": response}
            )
    else:
        raise HTTPException(status_code=401, detail="No token provided. Please log in.")


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
    context_processors=[current_year, authentication_in_header, user_image, user_name],
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


@router.get("/logout", dependencies=[Depends(is_authenticated)])
def logout(request: Request):
    response = RedirectResponse(request.url_for("root"), status_code=303)
    response.delete_cookie(key="access_token")
    return response


# Search user


@router.get("/search_user", dependencies=[Depends(is_authenticated)])
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


@router.get("/friend_requests", dependencies=[Depends(is_authenticated)])
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


@router.get("/single_chat", dependencies=[Depends(is_authenticated)])
async def single_chat(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        user = db.query(User).filter(User.id == user_id).first()

        users = (
            db.query(User)
            .join(Friend, (Friend.user1_id == User.id) | (Friend.user2_id == User.id))
            .filter(Friend.status == "accepted")
            .all()
        )

        users = [user for user in users if user.id != user_id]

        for user in users:
            user.avatar = b64encode(user.avatar).decode()

        channel_id = str(uuid4())

        new_channel = Channel(id=channel_id, user1_id=user_id, user2_id=user.id)
        db.add(new_channel)
        db.commit()

        return templates.TemplateResponse(
            "single_chat.html",
            {
                "request": request,
                "users": users,
                "user": user,
                "channel_id": channel_id,
            },
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Friend chat


@router.websocket("/friend_chat/{channel_id}")
async def websocket_endpoint(websocket: WebSocket, channel_id: str):
    await manager.connect(websocket)
    client_id = manager.get_client_id(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Client #{client_id} says: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"Client #{client_id} left the chat")


@router.get("/friend_chat/{channel_id}")
async def friend_chat_page(request: Request, channel_id: str):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()

        user_id = s.loads(token, max_age=3600).get("user_id")

        user = db.query(User).filter(User.id == user_id).first()
        
        channel = db.query(Channel).filter(Channel.id == channel_id).first()

        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        friends = db.query(Friend).filter(Friend.status == "accepted").all()
        friend_ids = [friend.user2_id for friend in friends]
        friend_ids.append(user_id)

        messages = db.query(Message).filter(Message.channel_id == channel_id).all()

        return templates.TemplateResponse(
            "friend_chat.html",
            {
                "request": request,
                "user": user,
                "messages": messages,
            },
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


@router.post("/friend_chat/{channel_id}")
async def friend_chat(request: Request, channel_id: str, message: str = Form(...)):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()

        user_id = s.loads(token, max_age=3600).get("user_id")

        user = db.query(User).filter(User.id == user_id).first()

        message_obj = Message(
            content=message,
            channel_id=channel_id,
            user_id=user_id,
            created_at=datetime.now(),
        )

        db.add(message_obj)
        db.commit()
        db.refresh(message_obj)

        messages = db.query(Message).filter(Message.channel_id == channel_id).all()

        return templates.TemplateResponse(
            "friend_chat.html", {"request": request, "messages": messages, "user": user}
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Group chat


@router.get("/group_chat", dependencies=[Depends(is_authenticated)])
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


@router.get("/create_group", dependencies=[Depends(is_authenticated)])
async def create_group(request: Request):
    return templates.TemplateResponse("create_group.html", {"request": request})


# Add friend


@router.get("/add_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
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


@router.get("/accept_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def accept_friend(request: Request, friend_id: int):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        friend = (
            db.query(Friend)
            .filter(Friend.user1_id == friend_id, Friend.user2_id == user_id)
            .first()
        )
        friend.status = "accepted"
        db.commit()
        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Deny friend requests


@router.get("/deny_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def deny_friend(request: Request, friend_id: int):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        friend = (
            db.query(Friend)
            .filter(Friend.user1_id == friend_id, Friend.user2_id == user_id)
            .first()
        )
        friend.status = "denied"
        db.commit()
        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Ai chat


def chatbot_response(user_input: str):
    model = GPT4All(model_name="gpt4all-falcon-q4_0.gguf")

    with model.chat_session():
        response = model.generate(prompt=f"{user_input}", temp=0)
        return model.current_chat_session[2]["content"]


@router.get("/chatbot", dependencies=[Depends(is_authenticated)])
async def chatbot_page(request: Request):
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
            "chatbot_chat.html",
            {"request": request, "user": user, "chatbot_messages": chatbot_messages},
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


@router.post("/chatbot", dependencies=[Depends(is_authenticated)])
async def chatbot(request: Request, message: str = Form(...)):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        user = db.query(User).filter(User.id == user_id).first()

        errors = {}

        if len(message) <= 0:
            errors["message"] = "Message cannot be empty"

        response = chatbot_response(message)

        chatbot_message = ChatbotMessage(
            user_id=user.id,
            message=message,
            response=response,
            created_at=datetime.now(),
        )
        db.add(chatbot_message)
        db.commit()

        chatbot_messages = (
            db.query(ChatbotMessage).filter(ChatbotMessage.user_id == user.id).all()
        )

        return templates.TemplateResponse(
            "chatbot_chat.html",
            {
                "request": request,
                "user": user,
                "message": message,
                "response": response,
                "chatbot_messages": chatbot_messages,
            },
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Clear past conversations with chatbot


@router.get("/clear_chatbot_messages", dependencies=[Depends(is_authenticated)])
async def clear_chatbot_messages(request: Request):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        db.query(ChatbotMessage).filter(ChatbotMessage.user_id == user_id).delete()
        db.commit()

        return templates.TemplateResponse("chatbot_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})
