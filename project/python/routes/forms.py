from dataclasses import dataclass
from typing import Optional

from fastapi import File, Form, UploadFile


@dataclass
class SignUpForm:
    name: str
    surname: str
    email: str
    password: str
    confirm_password: str
    terms_conditions: bool


@dataclass
class ProfileUpdateForm:
    avatar: Optional[UploadFile]
    name: Optional[str]
    surname: Optional[str]
    email: Optional[str]
    password: Optional[str]
    confirm_password: Optional[str]


def sign_up_form(
    name: str = Form(...),
    surname: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    terms_conditions: bool = Form(...),
) -> SignUpForm:
    return SignUpForm(
        name, surname, email, password, confirm_password, terms_conditions
    )


def profile_update_form(
    avatar: UploadFile = File(None),
    name: str = Form(None),
    surname: str = Form(None),
    email: str = Form(None),
    password: str = Form(None),
    confirm_password: str = Form(None),
) -> ProfileUpdateForm:
    return ProfileUpdateForm(avatar, name, surname, email, password, confirm_password)
