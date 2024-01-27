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

@app.websocket("/ws/friend_chat/")
async def websocket_endpoint(websocket: WebSocket):
    """_summary_

    Args:
        websocket (WebSocket): _description_
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_personal_message(f"You wrote: {data}", websocket)
            print(f"Client #{websocket.id} says: {data}")
            await manager.broadcast(f"Client says: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"Client # left the chat")


app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
