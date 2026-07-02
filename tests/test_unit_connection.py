from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from project.python.connection_manager import ConnectionManager


@pytest.fixture
def mgr():
    return ConnectionManager()


@pytest.fixture
def mock_ws():
    return AsyncMock()


@pytest.mark.asyncio
async def test_connection_manager_connect(mgr, mock_ws):
    await mgr.connect(mock_ws, "channel-1", 42)
    assert "channel-1" in mgr.active_connections
    assert mock_ws in mgr.active_connections["channel-1"]
    assert 42 in mgr.user_connections
    assert mock_ws in mgr.user_connections[42]
    assert 42 in mgr.online_users
    mock_ws.accept.assert_awaited_once()


@pytest.mark.asyncio
async def test_connection_manager_disconnect(mgr, mock_ws):
    mgr.active_connections["ch"] = [mock_ws]
    mgr.user_connections[1] = [mock_ws]
    mgr.online_users.add(1)
    mgr.disconnect(mock_ws, "ch", 1)

    assert mock_ws not in mgr.active_connections["ch"]
    assert 1 not in mgr.user_connections
    assert 1 not in mgr.online_users


@pytest.mark.asyncio
async def test_connection_manager_broadcast(mgr):
    mock_a = AsyncMock()
    mock_b = AsyncMock()
    mgr.active_connections["ch"] = [mock_a, mock_b]

    await mgr.broadcast("hello", "ch")
    mock_a.send_text.assert_awaited_once_with("hello")
    mock_b.send_text.assert_awaited_once_with("hello")


@pytest.mark.asyncio
async def test_connection_manager_broadcast_no_channel(mgr):
    await mgr.broadcast("hello", "nonexistent")
    assert True


@pytest.mark.asyncio
async def test_connection_manager_broadcast_except(mgr):
    mock_a = AsyncMock()
    mock_b = AsyncMock()
    mgr.active_connections["ch"] = [mock_a, mock_b]
    await mgr.broadcast_to_channel_except("hello", "ch", mock_a)
    mock_a.send_text.assert_not_awaited()
    mock_b.send_text.assert_awaited_once_with("hello")


def test_connection_manager_is_online(mgr):
    assert not mgr.is_online(1)
    mgr.online_users.add(1)
    assert mgr.is_online(1)


def test_get_other_user_ids_in_channel():
    mgr = ConnectionManager()
    ws_a = AsyncMock()
    ws_b = AsyncMock()

    mgr.active_connections["ch"] = [ws_a, ws_b]
    mgr._ws_to_user[id(ws_a)] = 1
    mgr._ws_to_user[id(ws_b)] = 2

    other_a = mgr.get_other_user_ids_in_channel("ch", ws_a)
    assert 2 in other_a
    assert 1 not in other_a

    other_b = mgr.get_other_user_ids_in_channel("ch", ws_b)
    assert 1 in other_b
    assert 2 not in other_b


def test_get_other_user_ids_in_channel_empty(mgr, mock_ws):
    mgr.active_connections["ch"] = [mock_ws]
    mgr._ws_to_user[id(mock_ws)] = 1
    assert mgr.get_other_user_ids_in_channel("ch", mock_ws) == []


def test_connection_manager_get_online_users(mgr):
    mgr.online_users.update({1, 2, 3})
    result = mgr.get_online_users()
    assert result == {1, 2, 3}
    assert result is not mgr.online_users


@pytest.mark.asyncio
async def test_disconnect_value_error_ws_not_in_channel(mgr, mock_ws):
    mgr.active_connections["ch"] = []
    mgr.user_connections[1] = [mock_ws]
    mgr.online_users.add(1)
    mgr.disconnect(mock_ws, "ch", 1)

    assert "ch" in mgr.active_connections
    assert 1 not in mgr.user_connections
    assert 1 not in mgr.online_users


@pytest.mark.asyncio
async def test_disconnect_value_error_ws_not_in_user_connections(mgr, mock_ws):
    mgr.active_connections["ch"] = [mock_ws]
    mgr.user_connections[1] = []
    mgr.online_users.add(1)
    mgr.disconnect(mock_ws, "ch", 1)

    assert mock_ws not in mgr.active_connections["ch"]
    assert 1 not in mgr.user_connections
    assert 1 not in mgr.online_users


@pytest.mark.asyncio
async def test_broadcast_websocket_disconnect(mgr):
    mock_ok = AsyncMock()
    mock_fail = AsyncMock()
    mock_fail.send_text.side_effect = WebSocketDisconnect()
    mgr.active_connections["ch"] = [mock_ok, mock_fail]

    await mgr.broadcast("hello", "ch")
    mock_ok.send_text.assert_awaited_once_with("hello")
    mock_fail.send_text.assert_awaited_once_with("hello")
    assert mock_fail not in mgr.active_connections["ch"]
    assert mock_ok in mgr.active_connections["ch"]


@pytest.mark.asyncio
async def test_broadcast_except_websocket_disconnect(mgr):
    mock_exclude = AsyncMock()
    mock_fail = AsyncMock()
    mock_fail.send_text.side_effect = WebSocketDisconnect()
    mgr.active_connections["ch"] = [mock_exclude, mock_fail]

    await mgr.broadcast_to_channel_except("hello", "ch", mock_exclude)
    mock_exclude.send_text.assert_not_awaited()
    mock_fail.send_text.assert_awaited_once_with("hello")
    assert mock_fail not in mgr.active_connections["ch"]
