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
from hashlib import sha256
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
from sqlalchemy.orm.exc import NoResultFound
from base64 import b64encode, b64decode
from g4f.client import Client
from database import SessionLocal
from models import User, Friend, ChatbotMessage, Message, Channel

router = APIRouter()


# Authentication


def authentication_in_header(request: Request):
    """Check if user is authenticated based on access token in header.

    Args:
        request (Request): The incoming request object.

    Returns:
        dict: A dictionary with a boolean indicating if the user is authenticated
    """
    token = request.cookies.get("access_token")
    if token:
        return {"is_authenticated": True}
    else:
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
    """Get user image from database.

    Args:
        request (Request): The request object

    Returns:
        dict: A dictionary with the user's image
    """

    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        try:
            user_id = s.loads(token, max_age=3600).get("user_id")
            db = SessionLocal()
            user = db.query(User).filter(User.id == user_id).first()
            user.avatar = b64encode(user.avatar).decode()
            return {"user_image": user.avatar}
        except:
            return {"user_image": ""}
    else:
        return {"user_image": ""}


# User name


def user_name(request: Request):
    """Get user name from database.

    Args:
        request (Request): The request object

    Returns:
        dict: A dictionary with the user's name
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
    """Get the current year.

    Args:
        request (Request): The request object

    Returns:
        dict: A dictionary with the current year
    """
    return {"current_year": datetime.now().year}


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
    context_processors=[current_year, authentication_in_header, user_image, user_name],
)

# Main page


@router.get("/")
def root(request: Request):
    """Render the home page.

    Args:
        request: The request object

    Returns:
        Response: Home page template response
    """
    return templates.TemplateResponse("main_page.html", {"request": request})


# Sign up


@router.get("/sign_up", name="sign_up")
def sign_up_page(request: Request):
    """Render the sign up page.

    Args:
        request: The request object

    Returns:
        Response: Sign up page template response
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
    """Render the login page.

    Args:
        request: The request object

    Returns:
        Response: Login page template response
    """
    return templates.TemplateResponse("login.html", {"request": request})


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
    """Send an email using SMTP.

    Args:
        email_address: The sender's email address
        subject: The email subject
        message: The email body

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
    """Render the contact page.

    Args:
        request: The request object

    Returns:
        Response: Contact page template response
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
    return templates.TemplateResponse(
        "main_page.html", {"request": request, "flash_messages": flash_messages}
    )


# Logout


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
        return templates.TemplateResponse("login.html", {"request": request})


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
        s = Serializer(environ.get("Secret_key_chat"))
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
            "search_user.html",
            {
                "request": request,
                "users": users,
                "friend_status_map": friend_status_map,
            },
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


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


# Update profile


@router.get("/update_profile", dependencies=[Depends(is_authenticated)])
async def update_profile_page(request: Request):
    """Render the update profile page.

    Args:
        request: The request object

    Returns:
        Response: Update profile page template
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
    token = request.cookies.get("access_token")
    if token:
        s = Serializer(environ.get("Secret_key_chat"))
        db = SessionLocal()
        user_id = s.loads(token, max_age=3600).get("user_id")
        user = db.query(User).filter(User.id == user_id).first()

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
        friend_avatar = None
        channel_ids = {}

        if friends:
            for friend in friends:
                friend_id = friend.id
                friend_avatar = b64encode(friend.avatar).decode()

                existing_channel = (
                    db.query(Channel)
                    .filter(
                        (Channel.user1_id == user_id) & (Channel.user2_id == friend_id)
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
                        channel_id=channel_id, user1_id=user_id, user2_id=friend_id
                    )
                    db.add(new_channel)
                    db.commit()
                    channel_ids[friend_id] = channel_id

                friend_status = (
                    db.query(Friend)
                    .filter(
                        ((Friend.user1_id == user_id) & (Friend.user2_id == friend_id))
                        | (
                            (Friend.user1_id == friend_id)
                            & (Friend.user2_id == user_id)
                        )
                    )
                    .first()
                )

                friend_status_value = friend_status.status if friend_status else None

        return templates.TemplateResponse(
            "single_chat.html",
            {
                "request": request,
                "friends": friends,
                "user": user,
                "friend_avatar": friend_avatar,
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
        s = Serializer(environ.get("Secret_key_chat"))
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

        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})


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
        s = Serializer(environ.get("Secret_key_chat"))
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

        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})


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
        s = Serializer(environ.get("Secret_key_chat"))
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

        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})


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
        s = Serializer(environ.get("Secret_key_chat"))
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

        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})


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
        s = Serializer(environ.get("Secret_key_chat"))
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

        return templates.TemplateResponse("single_chat.html", {"request": request})
    else:
        return templates.TemplateResponse("login.html", {"request": request})


# Ai chat


def chatbot_response(user_input: str):
    """
    Get a response from the chatbot for the given user input.

    Args:
        user_input (str): The user's message

    Returns:
        str: The chatbot's response
    """
    client = Client()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": user_input}],
    )
    chatbot_response = response.choices[0].message.content
    return chatbot_response


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
                "user_image": user.avatar,
                "chatbot_messages": chatbot_messages,
            },
        )
    else:
        return templates.TemplateResponse("login.html", {"request": request})


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
    """
    Clear all past chatbot messages for the user.

    Args:
        request (Request): The HTTP request

    Returns:
        TemplateResponse: The chatbot chat page
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
