from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
import uvicorn
from pathlib import Path
from routes import router, is_authenticated
from connection_manager import ConnectionManager


app = FastAPI()

manager = ConnectionManager()

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent.parent / "static"),
    name="static",
)


@app.websocket("/friend_chat/{channel_id}")
async def websocket_endpoint(websocket: WebSocket, channel_id: str):
    """_summary_

    Args:
        websocket (WebSocket): _description_
        channel_id (str): _description_
    """
    client_id = manager.get_client_id(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Client #{client_id} says: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"Client #{client_id} left the chat")


app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
