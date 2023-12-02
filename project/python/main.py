from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from pathlib import Path
from routes import router, templates

app = FastAPI()

app.mount(
   "/static",
   StaticFiles(directory=Path(__file__).parent.parent.absolute() / "static"),
   name="static"
)

app.include_router(router)

if __name__ == "__main__":
   uvicorn.run(app, host="127.0.0.1", port=8000)
