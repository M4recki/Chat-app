from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[WebSocket, str] = {}

    def get_client_id(self, websocket: WebSocket):
        """_summary_

        Args:
            websocket (WebSocket): _description_

        Returns:
            _type_: _description_
        """
        return self.active_connections[websocket]

    async def connect(self, websocket: WebSocket, client_id: str):
        """_summary_

        Args:
            websocket (WebSocket): _description_
            client_id (str): _description_
        """
        await websocket.accept()
        self.active_connections[websocket] = client_id

    def disconnect(self, websocket: WebSocket):
        """_summary_

        Args:
            websocket (WebSocket): _description_
        """
        del self.active_connections[websocket]

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """_summary_

        Args:
            message (str): _description_
            websocket (WebSocket): _description_
        """
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        """_summary_

        Args:
            message (str): _description_
        """
        for connection in self.active_connections:
            await connection.send_text(message)
