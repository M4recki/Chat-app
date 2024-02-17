from fastapi import (
    APIRouter,
    Request,
    Form,
    Depends,
    HTTPException,
    File,
    UploadFile,
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
from base64 import b64encode, b64decode
from uuid import uuid4
from gpt4all import GPT4All
from database import SessionLocal
from models import User, Friend, ChatbotMessage, Message, Channel

router = APIRouter()


# Authentication


def authentication_in_header(request: Request):
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
    token = request.cookies.get("access_token")
    if token:
        return {"is_authenticated": True}
    else:
        return {"is_authenticated": False}


def is_authenticated(request: Request):
    """_summary_

    Args:
        request (Request): _description_

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        try:
            user_id = s.loads(token, max_age=3600).get("user_id")
            db = SessionLocal()
            user = db.query(User).filter(User.id == user_id).first()
        except SignatureExpired:
            request.cookies.clear()
            return False
    else:
        return False


# Get user id


def get_user(user_id):
    db = SessionLocal()
    return db.query(User).filter(User.id == user_id).first()


# User image


def user_image(request: Request):
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
    return {"current_year": datetime.now().year}


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
    context_processors=[current_year, authentication_in_header, user_image, user_name],
)

# Main page


@router.get("/")
def root(request: Request):
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
    return templates.TemplateResponse("main_page.html", {"request": request})


# Sign up


@router.get("/sign_up", name="sign_up")
def sign_up_page(request: Request):
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_
        name (str, optional): _description_. Defaults to Form(...).
        surname (str, optional): _description_. Defaults to Form(...).
        email (str, optional): _description_. Defaults to Form(...).
        password (str, optional): _description_. Defaults to Form(...).
        confirm_password (str, optional): _description_. Defaults to Form(...).
        terms_conditions (bool, optional): _description_. Defaults to Form(...).

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_data(
    request: Request, email: str = Form(...), password: str = Form(...)
):
    """_summary_

    Args:
        request (Request): _description_
        email (str, optional): _description_. Defaults to Form(...).
        password (str, optional): _description_. Defaults to Form(...).

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        email_address (_type_): _description_
        subject (_type_): _description_
        message (_type_): _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
    return templates.TemplateResponse("contact.html", {"request": request})


@router.post("/contact")
async def contact_data(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
):
    """_summary_

    Args:
        request (Request): _description_
        name (str, optional): _description_. Defaults to Form(...).
        email (str, optional): _description_. Defaults to Form(...).
        subject (str, optional): _description_. Defaults to Form(...).
        message (str, optional): _description_. Defaults to Form(...).

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
    response = RedirectResponse(request.url_for("root"), status_code=303)
    response.delete_cookie(key="access_token")
    return response


# Search user


@router.get("/search_user", dependencies=[Depends(is_authenticated)])
async def search_user(request: Request):
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
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
            friend_request.user1.avatar = b64encode(friend_request.user1.avatar).decode()

        return templates.TemplateResponse(
            "friend_requests.html",
            {"request": request, "friend_requests": friend_requests},
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Update profile


@router.get("/update_profile", dependencies=[Depends(is_authenticated)])
async def update_profile_page(request: Request):
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        user = db.query(User).filter(User.id == user_id).first()

        return templates.TemplateResponse(
            "update_profile.html",
            {"request": request, "user": user, "errors": {}},
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


@router.post("/update_profile", dependencies=[Depends(is_authenticated)])
async def update_profile_data(
    request: Request,
    avatar: UploadFile = File(None),
    name: str = Form(None),
    surname: str = Form(None),
    email: str = Form(None),
    password: str = Form(None),
    confirm_password: str = Form(None),
):
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        user = db.query(User).filter(User.id == user_id).first()

        errors = {}

        if password is not None and not password.isalnum():
            errors["password"] = "Password must contain only letters and numbers"

        if password != confirm_password:
            errors["confirm_password"] = "Passwords do not match"

        if errors:
            return templates.TemplateResponse(
                "update_profile.html",
                {"request": request, "user": user, "errors": errors},
            )

        if avatar and avatar.content_type:
            if avatar.content_type not in ["image/jpeg", "image/png"]:
                errors["avatar"] = "Avatar must be a JPEG or PNG file"
            else:
                avatar_data = await avatar.read()
                img_binary = BytesIO()
                img_binary.write(avatar_data)
                user.avatar = img_binary.getvalue()

        updated_user = User(
            id=user_id,
            name=name,
            surname=surname,
            email=email,
            password=password,
            avatar=user.avatar,
        )
        db.commit()

        SECRET_KEY = environ.get("Secret_key_chat")
        s = Serializer(SECRET_KEY)
        token = s.dumps({"user_id": user_id})

        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Single chat


@router.get("/single_chat", dependencies=[Depends(is_authenticated)])
async def single_chat(request: Request):
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        user.avatar = b64decode(user.avatar)

        users = (
        db.query(User)
        .join(Friend, (Friend.user1_id == User.id) | (Friend.user2_id == User.id))
        .filter(
            (Friend.status == "accepted") | (Friend.status == "blocked")
        )
        .all()
    )

        # Show only friends

        users = [user for user in users if user.id != user_id]

        channel_id = ""
        for user in users:

            user.avatar = b64encode(user.avatar).decode()

            existing_channel = (
                db.query(Channel)
                .filter((Channel.user1_id == user_id) & (Channel.user2_id == user.id))
                .first()
            )
            if existing_channel:
                channel_id = existing_channel.channel_id
                break
            else:
                existing_channel = (
                    db.query(Channel)
                    .filter((Channel.user1_id == user.id) & (Channel.user2_id == user_id))
                    .first()
                )
                if existing_channel:
                    channel_id = existing_channel.channel_id
                    break
                else:
                    channel_id = str(uuid4())
                    new_channel = Channel(
                        channel_id=channel_id, user1_id=user_id, user2_id=user.id
                    )
                    db.add(new_channel)
                    db.commit()
                    break
                
        friend_id = user.id
                
        friend_status = (
                db.query(Friend)
                .filter(
                    (Friend.user1_id == user_id) & (Friend.user2_id == friend_id)
                    | (Friend.user1_id == friend_id) & (Friend.user2_id == user_id)
                )
                .first()
            )

        friend_status_value = friend_status.status if friend_status else None

        return templates.TemplateResponse(
            "single_chat.html",
            {
                "request": request,
                "users": users,
                "user": user,
                "user.avatar": user.avatar,
                "friend_status": friend_status_value,
                "channel_id": channel_id,
            },
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Friend chat


@router.get(
    "/friend_chat/{channel_id}/{friend_id}", dependencies=[Depends(is_authenticated)]
)
async def friend_chat_page(
    request: Request,
    channel_id: str,
    friend_id: int,
):
    """_summary_

    Args:
        request (Request): _description_
        channel_id (str): _description_

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()

        user_id = s.loads(token, max_age=3600).get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        user.avatar = b64encode(user.avatar).decode()

        friend = db.query(User).filter(User.id == friend_id).first()
        friend.avatar = b64encode(friend.avatar).decode()

        messages = db.query(Message).filter(Message.channel_id == channel_id).all()

        channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()

        friend_status = (
            db.query(Friend)
            .filter(
                (Friend.user1_id == user_id) & (Friend.user2_id == friend_id)
                | (Friend.user1_id == friend_id) & (Friend.user2_id == user_id)
            )
            .first()
        )

        friend_status_value = friend_status.status if friend_status else None

        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        return templates.TemplateResponse(
            "friend_chat.html",
            {
                "request": request,
                "user": user,
                "user.avatar": user.avatar,
                "friend": friend,
                "friend_status": friend_status_value,
                "friend.avatar": friend.avatar,
                "messages": messages,
                "channel_id": channel_id,
                "get_user": get_user,
            },
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Block friend


@router.get("/block_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def block_friend(request: Request, friend_id: int):
    """_summary_

    Args:
        request (Request): _description_
        friend_id (int): _description_

    Returns:
        _type_: _description_
    """    ''''''
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        existing_friendship = (
            db.query(Friend)
            .filter(
                (Friend.user1_id == user_id) & (Friend.user2_id == friend_id) |
                (Friend.user1_id == friend_id) & (Friend.user2_id == user_id)
            )
            .first()
        )

        new_friendship = Friend(
            user1_id=user_id,
            user2_id=friend_id,
            status="blocked",
            last_sent=datetime.now(),
        )
        db.add(new_friendship)
        db.commit()

        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})



# Unblock friend


@router.get("/unblock_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def unblock_friend(request: Request, friend_id: int):
    """_summary_

    Args:
        request (Request): _description_
        friend_id (int): _description_

    Returns:
        _type_: _description_
    """    ''''''
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        existing_friendship = (
            db.query(Friend)
            .filter(
                (Friend.user1_id == user_id) & (Friend.user2_id == friend_id) |
                (Friend.user1_id == friend_id) & (Friend.user2_id == user_id)
            )
            .first()
        )

        new_friendship = Friend(
            user1_id=user_id,
            user2_id=friend_id,
            status="accepted",
            last_sent=datetime.now(),
        )
        db.add(new_friendship)
        db.commit()

        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})

# Add friend


@router.get("/add_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def add_friend(request: Request, friend_id: int):
    """_summary_

    Args:
        request (Request): _description_
        friend_id (int): _description_

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_
        friend_id (int): _description_

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_
        friend_id (int): _description_

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        user_input (str): _description_

    Returns:
        _type_: _description_
    """
    model = GPT4All(model_name="gpt4all-falcon-q4_0.gguf")

    with model.chat_session():
        response = model.generate(prompt=f"{user_input}", temp=0)
        return model.current_chat_session[2]["content"]


@router.get("/chatbot", dependencies=[Depends(is_authenticated)])
async def chatbot_page(request: Request):
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        user = db.query(User).filter(User.id == user_id).first()

        user.avatar = b64encode(user.avatar).decode()

        chatbot_messages = (
            db.query(ChatbotMessage).filter(ChatbotMessage.user_id == user.id).all()
        )

        return templates.TemplateResponse(
            "chatbot_chat.html",
            {
                "request": request,
                "user": user,
                "user.avatar": user.avatar,
                "chatbot_messages": chatbot_messages,
            },
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


@router.post("/chatbot", dependencies=[Depends(is_authenticated)])
async def chatbot(request: Request, message: str = Form(...)):
    """_summary_

    Args:
        request (Request): _description_
        message (str, optional): _description_. Defaults to Form(...).

    Returns:
        _type_: _description_
    """
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
    """_summary_

    Args:
        request (Request): _description_

    Returns:
        _type_: _description_
    """
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
