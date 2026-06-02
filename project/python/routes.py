import logging
from base64 import b64encode
from datetime import datetime, timedelta
from email.message import EmailMessage
from hashlib import sha256
from importlib import import_module
from io import BytesIO
from os import environ
from pathlib import Path
from smtplib import SMTP_SSL
from ssl import create_default_context

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous.exc import BadSignature, SignatureExpired
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.security import check_password_hash, generate_password_hash

from .chatbot_utils import (ChatbotServiceError, chatbot_context,
                            chatbot_json_error, chatbot_json_success,
                            chatbot_response)
from .connection_manager import manager
from .database import session_scope
from .models import Channel, ChatbotMessage, Friend, Message, User
from .settings import settings

Image = import_module("PIL.Image")

router = APIRouter()
PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_AVATAR_PATH = PROJECT_DIR / "static" / "img" / "default avatar.png"


# Authentication


def authentication_in_header(request: object) -> dict:
    """Check if user is authenticated based on access token in header.

    Args:
        request (Request): The incoming request object.

    Returns:
        dict: A dictionary with a boolean indicating if the user
            is authenticated
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

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return True


def get_user_from_request(request: Request, max_age: int = 3600):
    """Get user object and ID from request based on access token.

    Args:
        request (Request): The request object
        max_age (int): The maximum age of the token in seconds

    Returns:
        tuple: A tuple containing the user object and user ID, or
            (None, None) if not found
    """
    token = request.cookies.get("access_token")
    if not token:
        return None, None

    s = Serializer(settings.chat_secret_key)
    try:
        user_id = s.loads(token, max_age=max_age).get("user_id")
    except (SignatureExpired, BadSignature):
        return None, None

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

    return user, user_id


def get_user(user_id):
    """Get user object from database by user ID.

    Args:
        user_id: The ID of the user to retrieve

    Returns:
        User: The user object if found, None otherwise"""
    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()
    return user


def encode_avatar(user):
    """Encode user avatar to base64 string for display in templates.

    Args:
        user: The user object containing the avatar binary data

    Returns:
        str: The base64-encoded avatar string, or an empty string
            if no avatar is found
    """
    if user and user.avatar:
        return b64encode(user.avatar).decode()
    return ""


# User image


def user_image(request: object):
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

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

    if user and user.avatar:
        return {"user_image": b64encode(user.avatar).decode()}
    return {"user_image": ""}


# User name


def user_name(request: object):
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

    with session_scope() as db:
        user = db.query(User).filter(User.id == user_id).first()

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
    """Render the sign-up page.

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
    with session_scope() as db:
        user = db.query(User).filter(User.email == email).first()

        errors = {}

        if user:
            errors["email"] = "User with this email already exists"

        if not password.isalnum():
            errors["password"] = (
                "Password must contain only letters and numbers"
            )

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
        db.commit()

    s = Serializer(settings.chat_secret_key)
    token = s.dumps({"user_id": new_user.id})

    response = RedirectResponse(
        request.url_for("single_chat"), status_code=303
    )
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
    with session_scope() as db:
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

    response = RedirectResponse(
        request.url_for("single_chat"), status_code=303
    )
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

    email_receiver = environ.get("EMAIL_RECEIVER", "")
    password = environ.get("EMAIL_PASSWORD", "")

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

    return render_template(
        "main_page.html", request, flash_messages=flash_messages
    )


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
        user_id = s.loads(token, max_age=3600).get("user_id")

        with session_scope() as db:
            users = db.query(User).filter(User.id != user_id).all()

            friend_statuses = (
                db.query(Friend)
                .filter(
                    (Friend.user1_id == user_id)
                    | (Friend.user2_id == user_id)
                )
                .all()
            )

            friend_status_map = {}
            channel_ids = {}
            for friend in friend_statuses:
                if friend.user1_id == user_id:
                    friend_id = friend.user2_id
                else:
                    friend_id = friend.user1_id

                friend_status_map[friend_id] = friend.status

                if friend.status == "accepted":
                    existing_channel = (
                        db.query(Channel)
                        .filter(
                            (
                                (Channel.user1_id == user_id)
                                & (Channel.user2_id == friend_id)
                            )
                            | (
                                (Channel.user1_id == friend_id)
                                & (Channel.user2_id == user_id)
                            )
                        )
                        .first()
                    )

                    if existing_channel:
                        channel_ids[friend_id] = existing_channel.channel_id
                    else:
                        channel_id = generate_channel_id(user_id, friend_id)
                        new_channel = Channel(
                            channel_id=channel_id,
                            user1_id=user_id,
                            user2_id=friend_id,
                        )
                        db.add(new_channel)
                        db.commit()
                        channel_ids[friend_id] = channel_id

            avatar_map = {
                u.id: b64encode(u.avatar).decode()
                for u in users if u.avatar
            }

        return templates.TemplateResponse(
            request,
            "search_user.html",
            {
                "request": request,
                "users": users,
                "avatar_map": avatar_map,
                "friend_status_map": friend_status_map,
                "channel_ids": channel_ids,
            },
        )
    else:
        return render_template("login.html", request)


# Friend requests


@router.get("/friend_requests", dependencies=[Depends(is_authenticated)])
async def friend_requests(request: Request):
    """Get pending friend requests for logged-in user.

    Args:
        request: The request object

    Returns:
        Response: Friend requests template
    """
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(settings.chat_secret_key)
        user_id = s.loads(token, max_age=3600).get("user_id")
        with session_scope() as db:
            friend_requests = (
                db.query(Friend)
                .filter(Friend.user2_id == user_id, Friend.status == "pending")
                .all()
            )
            friend_request_avatars = {
                fr.id: b64encode(fr.user1.avatar).decode()
                for fr in friend_requests
                if fr.user1.avatar
            }

        return templates.TemplateResponse(
            request,
            "friend_requests.html",
            {
                "request": request,
                "friend_requests": friend_requests,
                "friend_request_avatars": friend_request_avatars,
            },
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

    with session_scope() as db:
        updated_user = db.query(User).filter(User.id == user_id).first()
        if name is not None:
            updated_user.name = name
        if surname is not None:
            updated_user.surname = surname
        if email is not None:
            updated_user.email = email
        if password is not None:
            updated_user.password = password
        if avatar and avatar.content_type:
            updated_user.avatar = user.avatar
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

    with session_scope() as db:
        friends = (
            db.query(User)
            .join(
                Friend,
                (Friend.user1_id == User.id) | (Friend.user2_id == User.id),
            )
            .filter(
                Friend.status == "accepted",
                ((Friend.user1_id == user_id) & (User.id == Friend.user2_id))
                | (
                    (Friend.user2_id == user_id)
                    & (User.id == Friend.user1_id)
                ),
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
                        (Channel.user1_id == user_id)
                        & (Channel.user2_id == friend_id)
                        | (Channel.user1_id == friend_id)
                        & (Channel.user2_id == user_id)
                    )
                    .first()
                )

                if existing_channel:
                    channel_ids[friend_id] = existing_channel.channel_id
                else:
                    channel_id = generate_channel_id(user_id, friend_id)
                    new_channel = Channel(
                        channel_id=channel_id,
                        user1_id=user_id,
                        user2_id=friend_id,
                    )
                    db.add(new_channel)
                    db.commit()
                    channel_ids[friend_id] = channel_id

                friend_status = (
                    db.query(Friend)
                    .filter(
                        (Friend.user1_id == user_id)
                        & (Friend.user2_id == friend_id)
                        | (
                            (Friend.user1_id == friend_id)
                            & (Friend.user2_id == user_id)
                        )
                    )
                    .first()
                )

                friend_status_value = (
                    friend_status.status if friend_status else None
                )

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
    "/friend_chat/{channel_id}/{friend_id}",
    dependencies=[Depends(is_authenticated)],
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

    with session_scope() as db:
        friend = db.query(User).filter(User.id == friend_id).first()
        if not friend:
            raise HTTPException(status_code=404, detail="Friend not found")

        messages = (
            db.query(Message)
            .filter(Message.channel_id == channel_id)
            .all()
        )

        channel = (
            db.query(Channel)
            .filter(Channel.channel_id == channel_id)
            .first()
        )

        friend_status = (
            db.query(Friend)
            .filter(
                    (Friend.user1_id == user_id)
                    & (Friend.user2_id == friend_id)
                    | (Friend.user1_id == friend_id)
                    & (Friend.user2_id == user_id)
            )
            .first()
        )

        friend_status_value = (
            friend_status.status if friend_status else None
        )

        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

    avatar_b64 = encode_avatar(user)
    friend_avatar_b64 = encode_avatar(friend)

    return templates.TemplateResponse(
        request,
        "friend_chat.html",
        {
            "request": request,
            "user": user,
            "avatar_b64": avatar_b64,
            "friend": friend,
            "friend_avatar_b64": friend_avatar_b64,
            "friend_status": friend_status_value,
            "messages": messages,
            "channel_id": channel_id,
            "get_user": get_user,
        },
    )


# Block friend


@router.get(
    "/block_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
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
        user_id = s.loads(token, max_age=3600).get("user_id")

        with session_scope() as db:
            existing_friendship = (
                db.query(Friend)
                .filter(
                    (Friend.user1_id == user_id)
                    & (Friend.user2_id == friend_id)
                    | (Friend.user1_id == friend_id)
                    & (Friend.user2_id == user_id)
                )
                .first()
            )

            if existing_friendship:
                existing_friendship.status = "blocked"
                existing_friendship.last_sent = datetime.now()
                db.commit()
            else:
                new_friendship = Friend(
                    user1_id=user_id,
                    user2_id=friend_id,
                    status="blocked",
                    last_sent=datetime.now(),
                )
                db.add(new_friendship)
                db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


# Unblock friend


@router.get(
    "/unblock_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
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
        user_id = s.loads(token, max_age=3600).get("user_id")

        with session_scope() as db:
            existing_friendship = (
                db.query(Friend)
                .filter(
                    (Friend.user1_id == user_id)
                    & (Friend.user2_id == friend_id)
                    | (Friend.user1_id == friend_id)
                    & (Friend.user2_id == user_id)
                )
                .first()
            )

            if existing_friendship:
                existing_friendship.status = "accepted"
                existing_friendship.blocked_by_user = None
                existing_friendship.last_sent = datetime.now()
                db.commit()
            else:
                new_friendship = Friend(
                    user1_id=user_id,
                    user2_id=friend_id,
                    status="accepted",
                    last_sent=datetime.now(),
                )
                db.add(new_friendship)
                db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


# Add friend


@router.get(
    "/add_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
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
        user_id = s.loads(token, max_age=3600).get("user_id")

        with session_scope() as db:
            try:
                existing_request = (
                    db.query(Friend)
                    .filter(
                        (Friend.user1_id == user_id)
                        & (Friend.user2_id == friend_id)
                    )
                    .one()
                )

                if existing_request.status == "pending":
                    if (
                        datetime.now() - existing_request.last_sent
                        > timedelta(days=14)
                    ):
                        existing_request.last_sent = datetime.now()
                        db.commit()
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="Friend request already sent recently",
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


@router.get(
    "/accept_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
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
        user_id = s.loads(token, max_age=3600).get("user_id")

        with session_scope() as db:
            friend = (
                db.query(Friend)
                .filter(Friend.user1_id == friend_id,
                        Friend.user2_id == user_id)
                .first()
            )
            friend.status = "accepted"

            db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


# Deny friend requests


@router.get(
    "/deny_friend/{friend_id}",
    dependencies=[Depends(is_authenticated)],
)
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
        user_id = s.loads(token, max_age=3600).get("user_id")

        with session_scope() as db:
            friend = (
                db.query(Friend)
                .filter(Friend.user1_id == friend_id,
                        Friend.user2_id == user_id)
                .first()
            )
            friend.status = "denied"

            db.commit()

        return render_template("single_chat.html", request)
    else:
        return render_template("login.html", request)


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
    except Exception as exc:
        if isinstance(exc, ChatbotServiceError):
            logging.warning("Chatbot request failed: %s", exc)
            error_payload = {
                "error": "chatbot",
                "message": str(exc),
                "error_type": exc.__class__.__name__,
                "details": exc.details,
            }
        else:
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


@router.post(
    "/clear_chatbot_messages",
    dependencies=[Depends(is_authenticated)],
)
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

    with session_scope() as db:
        (
            db.query(ChatbotMessage)
            .filter(ChatbotMessage.user_id == user_id)
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


@router.get("/online-users")
async def online_users(request: Request):
    """Return the set of currently online user IDs as JSON.

    Args:
        request (Request): The HTTP request

    Returns:
        JSONResponse: A JSON object with online user IDs
    """
    return JSONResponse(
        content={"online_user_ids": list(manager.get_online_users())}
    )
