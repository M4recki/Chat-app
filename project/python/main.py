from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent.parent.absolute() / "static"),
    name="static"
)

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("main_page.html", {"request": request})
