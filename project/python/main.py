from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
from pathlib import Path
from routes import router

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent.parent.absolute() / "static"),
    name="static",
)

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
