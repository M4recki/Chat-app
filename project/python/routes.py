from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime

router = APIRouter()


def current_year(request: Request):
    return {"current_year": datetime.now().year}


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
    context_processors=[current_year]
)


@router.get("/")
def root(request: Request):
    return templates.TemplateResponse("main_page.html", {"request": request})
