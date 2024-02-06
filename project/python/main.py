from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn
from pathlib import Path
from routes import router, is_authenticated
from connection_manager import ConnectionManager


app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent.parent / "static"),
    name="static",
)

manager = ConnectionManager()


@app.websocket("/ws/{client_name}")
async def websocket_endpoint(websocket: WebSocket, client_name: str):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(
                f"<strong class='text-primary'>{client_name}:</strong> {data}"
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"{client_name} left the chat")


app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
