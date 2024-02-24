from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn
from pathlib import Path
from datetime import datetime
from json import dumps
from routes import router
from database import SessionLocal
from models import Message
from connection_manager import ConnectionManager


app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent.parent / "static"),
    name="static",
)


# Websocket


manager = ConnectionManager()


@app.websocket("/ws/{channel_id}/{user_name}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket, channel_id: str, user_name: str, user_id: int
):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()

            # Create a message object in JSON format
            message_object = {
                "userId": user_id,
                "senderName": user_name,
                "content": data,
            }

            await manager.broadcast(dumps(message_object))

            db = SessionLocal()

            new_message = Message(
                content=data,
                channel_id=channel_id,
                created_at=datetime.now(),
                user_id=user_id,
            )
            db.add(new_message)
            db.commit()

            messages = db.query(Message).filter(Message.channel_id == channel_id).all()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(dumps({"type": "system", "content": f"{user_name} left the chat"}))


app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
