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
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from werkzeug.security import generate_password_hash, check_password_hash
from hashlib import sha256
from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous.exc import SignatureExpired, BadSignature
from pathlib import Path
from datetime import datetime, timedelta
from email.message import EmailMessage
from ssl import create_default_context
from smtplib import SMTP_SSL
import logging
from os import environ
from importlib import import_module
from io import BytesIO
from sqlalchemy.orm.exc import NoResultFound
from base64 import b64encode, b64decode
from openai import OpenAI
from .database import SessionLocal
from .settings import settings
from .models import User, Friend, ChatbotMessage, Message, Channel

Image = import_module("PIL.Image")

router = APIRouter()
PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_AVATAR_PATH = PROJECT_DIR / "static" / "img" / "default avatar.png"


# Authentication


def authentication_in_header(request: Request):
    """Check if user is authenticated based on access token in header.

    Args:
        request (Request): The incoming request object.

    Returns:
        dict: A dictionary with a boolean indicating if the user is authenticated
    """
    if not isinstance(request, Request):
        return {"is_authenticated": False}
    token = request.cookies.get("access_token")
    if not token:
        return {"is_authenticated": False}

    s = Serializer(settings.chat_secret_key)
    try:
        s.loads(token, max_age=settings.token_max_age)
        return {"is_authenticated": True}
    except (SignatureExpired, BadSignature):
        return {"is_authenticated": False}


def is_authenticated(request: Request):
    """Check if user is authenticated based on access token.

    Args:
        request (Request): The request object

    Raises:
        HTTPException: Error description

    Returns:
        bool: True if user is authenticated, False otherwise
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    s = Serializer(settings.chat_secret_key)
    try:
        user_id = s.loads(token, max_age=settings.token_max_age).get("user_id")
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Session expired")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid session token")

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return True


# Get user id


def get_user(user_id):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()
    return user


def get_user_from_request(request: Request, max_age: int = 3600):
    token = request.cookies.get("access_token")
    if not token:
        return None, None

    s = Serializer(settings.chat_secret_key)
    try:
        user_id = s.loads(token, max_age=max_age).get("user_id")
    except (SignatureExpired, BadSignature):
        return None, None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()

    return user, user_id


def encode_avatar(user):
    if user and user.avatar:
        return b64encode(user.avatar).decode()
    return ""


# User image


def user_image(request: Request):
    """Get user image from database.

    Args:
        request (Request): The request object

    Returns:
        dict: A dictionary with the user's image
    """
    if not isinstance(request, Request):
        return {"user_image": ""}

    token = request.cookies.get("access_token")
    if not token:
        return {"user_image": ""}

    s = Serializer(settings.chat_secret_key)
    try:
        user_id = s.loads(token, max_age=3600).get("user_id")
    except (SignatureExpired, BadSignature):
        return {"user_image": ""}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()

    if user and user.avatar:
        user.avatar = b64encode(user.avatar).decode()
        return {"user_image": user.avatar}
    return {"user_image": ""}


# User name


def user_name(request: Request):
    """Get user name from database.

    Args:
        request (Request): The request object

    Returns:
        dict: A dictionary with the user's name
    """
    if not isinstance(request, Request):
        return {"user_name": None}

    token = request.cookies.get("access_token")
    if not token:
        return {"user_name": None}

    s = Serializer(settings.chat_secret_key)
    try:
        user_id = s.loads(token, max_age=3600).get("user_id")
    except (SignatureExpired, BadSignature):
        return {"user_name": None}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()

    if user:
        return {"user_name": user.name}
    return {"user_name": None}


# Current year in footer


def current_year(request: Request):
    """Get the current year.

    Args:
        request (Request): The request object

    Returns:
        dict: A dictionary with the current year
    """
    return {"current_year": datetime.now().year}


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
    context_processors=[
        authentication_in_header,
        user_image,
        user_name,
        current_year,
    ],
)


def render_template(name: str, request: Request, **kwargs):
    """Render template with auto-injected context data.

    Args:
        name: Template filename
        request: Request object
        **kwargs: Additional context variables

    Returns:
        HTMLResponse with rendered template
    """
    context = {"request": request}
    context.update(authentication_in_header(request))
    context.update(user_image(request))
    context.update(user_name(request))
    context.update(current_year(request))
    context.update(kwargs)
    template = templates.get_template(name)
    html_content = template.render(context)

    return HTMLResponse(content=html_content)


# Main page


@router.get("/")
def root(request: Request):
    """Render the home page.

    Args:
        request: The request object

    Returns:
        Response: Home page template response
    """
    return render_template("main_page.html", request)


# Sign up


@router.get("/sign_up", name="sign_up")
def sign_up_page(request: Request):
    """Render the sign up page.

    Args:
        request: The request object

    Returns:
        Response: Sign up page template response
    """
    return render_template("sign_up.html", request, errors={})


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
        return render_template("sign_up.html", request, errors=errors)

    hashed_password = generate_password_hash(
        password, method="pbkdf2:sha256", salt_length=6
    )

    img_binary = BytesIO()
    with Image.open(DEFAULT_AVATAR_PATH) as img:
        img.save(img_binary, format="PNG")
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

    s = Serializer(settings.chat_secret_key)
    token = s.dumps({"user_id": new_user.id})

    response = RedirectResponse(request.url_for("single_chat"), status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True)

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


@router.post("/login")
async def login_data(
    request: Request, email: str = Form(...), password: str = Form(...)
):
    """Handle login form submission.

    Args:
        request: The request object
        email: The email form field
        password: The password form field

    Returns:
        Response: Redirect or login template on validation errors
    """
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()

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
    response.set_cookie(key="access_token", value=token, httponly=True)

    return response


# Contact


def send_email(email_address, subject, message):
    """Send an email using SMTP.

    Args:
        email_address: The sender's email address
        subject: The email subject
        message: The email body

    """
    # During tests sending real emails is disabled.
    if environ.get("TESTING") == "1":
        return

    email_receiver = environ.get("EMAIL_RECEIVER")
    password = environ.get("EMAIL_PASSWORD")

    email = EmailMessage()

    email["From"] = email_address
    email["To"] = email_receiver
    email["Subject"] = subject
    email.set_content(message)

    context = create_default_context()

    with SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
        smtp.login(email_receiver, password)
        smtp.sendmail(email_address, email_receiver, email.as_string())


@router.get("/contact", name="contact")
def contact_page(request: Request):
    """Render the contact page.

    Args:
        request: The request object

    Returns:
        Response: Contact page template response
    """
    return render_template("contact.html", request)


@router.post("/contact")
async def contact_data(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
):
    """Handle contact form submission.

    Args:
        request: The request object
        name: The name form field
        email: The email form field
        subject: The subject form field
        message: The message form field

    Returns:
        Response: Redirect to home page on success
    """
    errors = {}

    if len(message) < 10:
        errors["message"] = "Message must contain at least 10 characters"

    send_email(email, subject, message)
    flash_messages = ["Your message has been sent"]

    return render_template("main_page.html", request, flash_messages=flash_messages)


@router.get("/logout", dependencies=[Depends(is_authenticated)])
def logout(request: Request):
    """Logout the currently authenticated user.

    Args:
        request: The request object

    Returns:
        Response: Redirect to login or home page
    """
    token = request.cookies.get("access_token")
    if token:
        response = RedirectResponse(request.url_for("root"), status_code=303)
        response.delete_cookie(key="access_token")
        return response
    else:
        return render_template("login.html", request)


# Search user


@router.get("/search_user", dependencies=[Depends(is_authenticated)])
async def search_user(request: Request):
    """Search for and return other users.

    Args:
        request: The request object

    Returns:
        Response: User search template
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        users = db.query(User).filter(User.id != user_id).all()

        friend_statuses = (
            db.query(Friend)
            .filter((Friend.user1_id == user_id) | (Friend.user2_id == user_id))
            .all()
        )

        friend_status_map = {}
        for friend in friend_statuses:
            if friend.user1_id == user_id:
                friend_status_map[friend.user2_id] = friend.status
            else:
                friend_status_map[friend.user1_id] = friend.status

        for user in users:
            user.avatar = b64encode(user.avatar).decode()

        return templates.TemplateResponse(
            request,
            "search_user.html",
            {
                "request": request,
                "users": users,
                "friend_status_map": friend_status_map,
            },
        )
    else:
        return render_template("login.html", request)


# Friend requests


@router.get("/friend_requests", dependencies=[Depends(is_authenticated)])
async def friend_requests(request: Request):
    """Get pending friend requests for logged in user.

    Args:
        request: The request object

    Returns:
        Response: Friend requests template
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
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
            request,
            "friend_requests.html",
            {"request": request, "friend_requests": friend_requests},
        )
    else:
        return render_template("login.html", request)


# Update profile


@router.get("/update_profile", dependencies=[Depends(is_authenticated)])
async def update_profile_page(request: Request):
    """Render the update profile page.

    Args:
        request: The request object

    Returns:
        Response: Update profile page template
    """
    user, _ = get_user_from_request(request)
    if not user:
        return render_template("login.html", request)

    return templates.TemplateResponse(
        request,
        "update_profile.html",
        {"request": request, "user": user, "errors": {}},
    )


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
    """Handle update profile form submission.

    Args:
        request: The request object
        avatar: The avatar upload field
        name: The name form field
        surname: The surname form field
        email: The email form field
        password: The password form field
        confirm_password: The confirm password form field

    Returns:
        Response: Redirect or update profile template
    """
    user, user_id = get_user_from_request(request)
    if not user:
        return render_template("login.html", request)

    db = SessionLocal()
    errors = {}

    if password is not None and not password.isalnum():
        errors["password"] = "Password must contain only letters and numbers"

    if password != confirm_password:
        errors["confirm_password"] = "Passwords do not match"

    if errors:
        return templates.TemplateResponse(
            request,
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

    return render_template("single_chat.html", request)


# Generate random channel id


def generate_channel_id(user1_id, user2_id):
    """Generate a unique channel ID.

    Args:
        user1_id: ID of first user
        user2_id: ID of second user

    Returns:
        str: The generated channel ID
    """
    unique_string = f"{user1_id}{user2_id}"
    return sha256(unique_string.encode()).hexdigest()


# Single chat


@router.get("/single_chat", dependencies=[Depends(is_authenticated)])
async def single_chat(request: Request):
    """Display the user's chat channels.

    Args:
        request: The request object

    Returns:
        Response: Single chat template
    """
    user, user_id = get_user_from_request(request)
    if not user:
        return render_template("login.html", request)

    db = SessionLocal()

    friends = (
        db.query(User)
        .join(Friend, (Friend.user1_id == User.id) | (Friend.user2_id == User.id))
        .filter(
            Friend.status == "accepted",
            ((Friend.user1_id == user_id) & (User.id == Friend.user2_id))
            | ((Friend.user2_id == user_id) & (User.id == Friend.user1_id)),
        )
        .all()
    )

    friend_status_value = None
    friend_avatars = {}
    channel_ids = {}

    if friends:
        for friend in friends:
            friend_id = friend.id
            friend_avatars[friend_id] = b64encode(friend.avatar).decode()

            existing_channel = (
                db.query(Channel)
                .filter(
                    (Channel.user1_id == user_id) & (Channel.user2_id == friend_id)
                    | (Channel.user1_id == friend_id) & (Channel.user2_id == user_id)
                )
                .first()
            )

            if existing_channel:
                channel_ids[friend_id] = existing_channel.channel_id
            else:
                channel_id = generate_channel_id(user_id, friend_id)
                new_channel = Channel(
                    channel_id=channel_id, user1_id=user_id, user2_id=friend_id
                )
                db.add(new_channel)
                db.commit()
                channel_ids[friend_id] = channel_id

            friend_status = (
                db.query(Friend)
                .filter(
                    ((Friend.user1_id == user_id) & (Friend.user2_id == friend_id))
                    | ((Friend.user1_id == friend_id) & (Friend.user2_id == user_id))
                )
                .first()
            )

            friend_status_value = friend_status.status if friend_status else None

    return templates.TemplateResponse(
        request,
        "single_chat.html",
        {
            "request": request,
            "friends": friends,
            "user": user,
            "friend_avatars": friend_avatars,
            "friend_status": friend_status_value,
            "channel_ids": channel_ids,
        },
    )


# Friend chat


@router.get(
    "/friend_chat/{channel_id}/{friend_id}", dependencies=[Depends(is_authenticated)]
)
async def friend_chat_page(
    request: Request,
    channel_id: str,
    friend_id: int,
):
    """
    Retrieve chat messages for a friend chat channel.

    Args:
        request (Request): The HTTP request object
        channel_id (str): The ID of the chat channel
        friend_id (int): The ID of the friend

    Raises:
        HTTPException: If the channel is not found

    Returns:
        TemplateResponse: Rendered template with chat context
    """
    user, user_id = get_user_from_request(request)
    if not user:
        return render_template("login.html", request)

    db = SessionLocal()

    user.avatar = encode_avatar(user)

    friend = db.query(User).filter(User.id == friend_id).first()
    friend.avatar = encode_avatar(friend)

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
        request,
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


# Block friend


@router.get("/block_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def block_friend(request: Request, friend_id: int):
    """
    Block a friend from the user's friend list.

    Args:
        request (Request): The HTTP request object
        friend_id (int): The ID of the friend to block

    Returns:
        TemplateResponse: Rendered template on success
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        existing_friendship = (
            db.query(Friend)
            .filter(
                (Friend.user1_id == user_id) & (Friend.user2_id == friend_id)
                | (Friend.user1_id == friend_id) & (Friend.user2_id == user_id)
            )
            .first()
        )

        if existing_friendship:
            existing_friendship.status = "blocked"
            db.commit()

        updated_friendship = Friend(
            user1_id=user_id,
            user2_id=friend_id,
            status="blocked",
        )
        db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


# Unblock friend


@router.get("/unblock_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def unblock_friend(request: Request, friend_id: int):
    """
    Unblock a previously blocked friend.

    Args:
        request (Request): The HTTP request object
        friend_id (int): The ID of the friend to unblock

    Returns:
        TemplateResponse: Rendered template on success
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        existing_friendship = (
            db.query(Friend)
            .filter(
                (Friend.user1_id == user_id) & (Friend.user2_id == friend_id)
                | (Friend.user1_id == friend_id) & (Friend.user2_id == user_id)
            )
            .first()
        )

        if existing_friendship:
            existing_friendship.status = "accepted"
            db.commit()

        updated_friendship = Friend(
            user1_id=user_id,
            user2_id=friend_id,
            status="accepted",
            blocked_by_user=friend_id,
        )
        db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


# Add friend


@router.get("/add_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def add_friend(request: Request, friend_id: int):
    """
    Add a friend request.

    Checks if a pending or denied request already exists,
    updates it if needed or creates a new one.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend

    Raises:
        HTTPException: If request already sent recently

    Returns:
        TemplateResponse: On success
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        try:
            existing_request = (
                db.query(Friend)
                .filter((Friend.user1_id == user_id) & (Friend.user2_id == friend_id))
                .one()
            )

            if existing_request.status == "pending":
                if datetime.now() - existing_request.last_sent > timedelta(days=14):
                    existing_request.last_sent = datetime.now()
                    db.commit()
                else:
                    raise HTTPException(
                        status_code=400, detail="Friend request already sent recently"
                    )
            elif existing_request.status == "denied":
                existing_request.status = "pending"
                existing_request.last_sent = datetime.now()
                db.commit()

        except NoResultFound:
            new_friendship = Friend(
                user1_id=user_id,
                user2_id=friend_id,
                status="pending",
                last_sent=datetime.now(),
            )
            db.add(new_friendship)
            db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


# Accept friend requests


@router.get("/accept_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def accept_friend(request: Request, friend_id: int):
    """
    Accept a pending friend request.

    Updates the friend request status to accepted.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend

    Returns:
        TemplateResponse: On success
    """

    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        friend = (
            db.query(Friend)
            .filter(Friend.user1_id == friend_id, Friend.user2_id == user_id)
            .first()
        )
        friend.status = "accepted"

        friends = (
            db.query(User)
            .join(Friend, (Friend.user1_id == User.id) | (Friend.user2_id == User.id))
            .filter(
                Friend.status == "accepted",
                ((Friend.user1_id == user_id) & (User.id == Friend.user2_id))
                | ((Friend.user2_id == user_id) & (User.id == Friend.user1_id)),
            )
            .all()
        )

        db.commit()

        for friend in friends:
            friend.avatar = b64encode(friend.avatar).decode()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


# Deny friend requests


@router.get("/deny_friend/{friend_id}", dependencies=[Depends(is_authenticated)])
async def deny_friend(request: Request, friend_id: int):
    """
    Deny a pending friend request.

    Updates the friend request status to denied.

    Args:
        request (Request): The HTTP request
        friend_id (int): The ID of the friend

    Returns:
        TemplateResponse: On success
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")

        friend = (
            db.query(Friend)
            .filter(Friend.user1_id == friend_id, Friend.user2_id == user_id)
            .first()
        )
        friend.status = "denied"

        friends = (
            db.query(User)
            .join(Friend, (Friend.user1_id == User.id) | (Friend.user2_id == User.id))
            .filter(
                Friend.status == "accepted",
                ((Friend.user1_id == user_id) & (User.id == Friend.user2_id))
                | ((Friend.user2_id == user_id) & (User.id == Friend.user1_id)),
            )
            .all()
        )

        for friend in friends:
            friend.avatar = b64encode(friend.avatar).decode()

        db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


# Chatbot
# TODO: Add optional memory of past messages and system instructions to chatbot_response function, markdown formatting support in chatbot responses and smoketest + edge case tests for chatbot functionality


def chatbot_response(user_input: str):
    """
    Get a response from the chatbot for the given user input.

    Args:
        user_input (str): The user's message

    Returns:
        str: The chatbot's response
    """
    # In testing skip external API calls and return deterministic result
    if environ.get("TESTING") == "1":
        if ":" in user_input:
            return user_input.split(":", 1)[1].strip()
        return "test-response"

    api_key = settings.ai_key.strip().strip('"').strip("'")
    if api_key.lower().startswith("bearer "):
        api_key = api_key.split(" ", 1)[1].strip()
    if not api_key or api_key.lower() in {"your-nvidia-api-key", "changeme"}:
        return "Chatbot service is not configured"

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
    )
    completion = client.chat.completions.create(
        model="stepfun-ai/step-3.5-flash",
        messages=[{"role": "user", "content": user_input}],
        temperature=1,
        top_p=0.9,
        max_tokens=16384,
        stream=False,
    )

    message = completion.choices[0].message
    content = message.content if message else None
    if not content:
        return "Chatbot returned an empty response"

    return content


# Helper functions for chatbot context and JSON responses


def chatbot_context(user, chatbot_messages, **extra):
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
    return JSONResponse(status_code=status_code, content=payload)


def chatbot_json_success(message: str, response: str, created_at: datetime):
    return JSONResponse(
        status_code=200,
        content={
            "message": message,
            "response": response,
            "created_at": created_at.strftime(" %H:%M, %Y-%m-%d"),
        },
    )


@router.get("/chatbot", dependencies=[Depends(is_authenticated)])
async def chatbot_page(request: Request):
    """
    Render the chatbot chat page.

    Retrieves the logged in user and their past chatbot messages.

    Args:
        request (Request): The HTTP request

    Returns:
        TemplateResponse: The chatbot chat page
    """
    user, user_id = get_user_from_request(request)
    if not user:
        return render_template("login.html", request)

    db = SessionLocal()
    user.avatar = encode_avatar(user)

    chatbot_messages = (
        db.query(ChatbotMessage).filter(ChatbotMessage.user_id == user.id).all()
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


@router.post("/chatbot", dependencies=[Depends(is_authenticated)])
async def chatbot(request: Request, message: str = Form(...)):
    """
    Send a new message to the chatbot.

    Saves the user message and chatbot response to the database.

    Args:
        request (Request): The HTTP request
        message (str): The user's message

    Returns:
        TemplateResponse: The chatbot chat page
    """
    user, user_id = get_user_from_request(request)
    if not user:
        return render_template("login.html", request)

    db = SessionLocal()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    errors = {}
    if len(message) <= 0:
        errors["message"] = "Message cannot be empty"

    if errors:
        if is_ajax:
            return chatbot_json_error(400, {"error": "validation", "details": errors})
        return templates.TemplateResponse(
            request,
            "chatbot_chat.html",
            chatbot_context(user, [], request=request, message=message, errors=errors),
        )

    try:
        response = chatbot_response(message)
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
                user, [], request=request, message=message, errors=error_payload
            ),
        )

    chatbot_message = ChatbotMessage(
        user_id=user.id,
        message=message,
        response=response,
        created_at=datetime.now(),
    )
    db.add(chatbot_message)
    db.commit()

    if is_ajax:
        return chatbot_json_success(message, response, chatbot_message.created_at)

    chatbot_messages = (
        db.query(ChatbotMessage).filter(ChatbotMessage.user_id == user.id).all()
    )

    return templates.TemplateResponse(
        request,
        "chatbot_chat.html",
        chatbot_context(
            user, chatbot_messages, request=request, message=message, response=response
        ),
    )


# Clear past conversations with chatbot


@router.get("/clear_chatbot_messages", dependencies=[Depends(is_authenticated)])
async def clear_chatbot_messages(request: Request):
    """
    Clear all past chatbot messages for the user.

    Args:
        request (Request): The HTTP request

    Returns:
        TemplateResponse: The chatbot chat page
    """
    user, user_id = get_user_from_request(request)
    if not user:
        return render_template("login.html", request)

    db = SessionLocal()

    db.query(ChatbotMessage).filter(ChatbotMessage.user_id == user_id).delete()
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
