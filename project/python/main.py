from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

app = FastAPI()

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

@app.get("/")
async def root(request: Request):
   return templates.TemplateResponse("index.html", {"request": request})
