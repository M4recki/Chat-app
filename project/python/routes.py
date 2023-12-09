from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pathlib import Path
from datetime import datetime

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
async def sign_up_page(request: Request):
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
    redirect_url = request.url_for("root")
    return RedirectResponse(redirect_url, status_code=303)


# Login


@router.get("/login", name="login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_data(request: Request, email: str = Form(...), password: str = Form(...)):
    redirect_url = request.url_for("root")
    return RedirectResponse(redirect_url, status_code=303)


# Contact


@router.get("/contact", name="contact")
async def contact_page(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})


@router.post("/contact")
async def contact_data(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
):
    redirect_url = request.url_for("root")
    return RedirectResponse(redirect_url, status_code=303)
