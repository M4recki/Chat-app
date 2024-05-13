from fastapi import WebSocket


class ConnectionManager:
    """
    Manages active websocket connections to channels.

    Keeps track of open websocket connections mapped to channels.
    """

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel_id: str):
        """
        Connect a websocket to a channel.

        Args:
            websocket (WebSocket): The websocket to connect
            channel_id (str): The channel ID
        """
        await websocket.accept()
        if channel_id not in self.active_connections:
            self.active_connections[channel_id] = []
        self.active_connections[channel_id].append(websocket)

    def disconnect(self, websocket: WebSocket, channel_id: str):
        """
        Disconnect a websocket from a channel.

        Args:
            websocket (WebSocket): The websocket to disconnect
            channel_id (str): The channel ID
        """
        if channel_id in self.active_connections:
            self.active_connections[channel_id].remove(websocket)

    async def broadcast(self, message: str, channel_id: str):
        """
        Broadcast a message to all connections in a channel.

        Args:
            message (str): The message to send
            channel_id (str): The channel ID
        """
        if channel_id in self.active_connections:
            for connection in self.active_connections[channel_id]:
                await connection.send_text(message)
