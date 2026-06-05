from __future__ import annotations

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    """
    Manages active websocket connections to channels.

    Keeps track of open websocket connections mapped to channels
    and global online user presence.
    """

    def __init__(self) -> None:
        """Initialize empty connection stores and online user set."""
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.user_connections: dict[int, list[WebSocket]] = {}
        self.online_users: set[int] = set()
        self._ws_to_user: dict[int, int] = {}

    async def connect(
            self, websocket: WebSocket, channel_id: str, user_id: int
    ):
        """
        Connect a websocket to a channel and mark user as online.

        Args:
            websocket (WebSocket): The websocket to connect
            channel_id (str): The channel ID
            user_id (int): The user ID
        """
        await websocket.accept()
        if channel_id not in self.active_connections:
            self.active_connections[channel_id] = []
        self.active_connections[channel_id].append(websocket)

        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(websocket)

        self.online_users.add(user_id)
        self._ws_to_user[id(websocket)] = user_id

    def disconnect(self, websocket: WebSocket, channel_id: str, user_id: int):
        """
        Disconnect a websocket from a channel and clean up user presence.

        Args:
            websocket (WebSocket): The websocket to disconnect
            channel_id (str): The channel ID
            user_id (int): The user ID
        """
        if channel_id in self.active_connections:
            try:
                self.active_connections[channel_id].remove(websocket)
            except ValueError:
                pass

        if user_id in self.user_connections:
            try:
                self.user_connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
                self.online_users.discard(user_id)

        self._ws_to_user.pop(id(websocket), None)

    async def broadcast(self, message: str, channel_id: str):
        """
        Broadcast a message to all connections in a channel.

        Args:
            message (str): The message to send
            channel_id (str): The channel ID
        """
        if channel_id in self.active_connections:
            dead = []
            for connection in self.active_connections[channel_id]:
                try:
                    await connection.send_text(message)
                except (WebSocketDisconnect, RuntimeError):
                    dead.append(connection)
            for connection in dead:
                self.active_connections[channel_id].remove(connection)

    async def broadcast_to_channel_except(
            self, message: str, channel_id: str, exclude_websocket: WebSocket
    ):
        """
        Broadcast a message to all connections in a channel except one.

        Args:
            message (str): The message to send
            channel_id (str): The channel ID
            exclude_websocket (WebSocket): The websocket to exclude
        """
        if channel_id in self.active_connections:
            dead = []
            for connection in self.active_connections[channel_id]:
                if connection == exclude_websocket:
                    continue
                try:
                    await connection.send_text(message)
                except (WebSocketDisconnect, RuntimeError):
                    dead.append(connection)
            for connection in dead:
                self.active_connections[channel_id].remove(connection)



    def get_other_user_ids_in_channel(
            self, channel_id: str, exclude_websocket: WebSocket
    ) -> list[int]:
        """
        Get user IDs of all other connections in a channel.

        Args:
            channel_id (str): The channel ID
            exclude_websocket (WebSocket): The websocket to exclude

        Returns:
            list[int]: List of user IDs
        """
        other_ids: set[int] = set()
        for ws in self.active_connections.get(channel_id, []):
            if ws != exclude_websocket:
                uid = self._ws_to_user.get(id(ws))
                if uid is not None:
                    other_ids.add(uid)
        return list(other_ids)

    def is_online(self, user_id: int) -> bool:
        """
        Check if a user is currently online.

        Args:
            user_id (int): The user ID

        Returns:
            bool: True if the user has active connections
        """
        return user_id in self.online_users

    def get_online_users(self) -> set[int]:
        """
        Get the set of currently online user IDs.

        Returns:
            set[int]: Set of online user IDs
        """
        return self.online_users.copy()


manager = ConnectionManager()
