from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn
from pathlib import Path
from datetime import datetime
from json import dumps, loads
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
    await manager.connect(websocket, channel_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = loads(data)
            channel_id = message_data["channel_id"]
            message = message_data["message"]

            # Create a message object in JSON format
            message_object = {
                "userId": user_id,
                "senderName": user_name,
                "content": message,
            }

            await manager.broadcast(dumps(message_object), channel_id)

            db = SessionLocal()

            new_message = Message(
                content=message,
                channel_id=channel_id,
                created_at=datetime.now(),
                user_id=user_id,
            )
            db.add(new_message)
            db.commit()

            messages = db.query(Message).filter(Message.channel_id == channel_id).all()

    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id)
        await manager.broadcast(
            dumps({"type": "system", "content": f"{user_name} left the chat"}),
            channel_id,
        )


app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
