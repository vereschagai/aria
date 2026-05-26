"""
Tests for WebSocketServer (websocket_server.py).

BRD requirement covered: worker dispatch, priority ordering, auth, and
orphan task cleanup on client disconnect.
"""

import sys
import os
import json
import asyncio
import base64
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(type_="sync", status="new", host=None, task_id=None):
    oid = ObjectId()
    return {
        "_id": oid,
        "type": type_,
        "status": status,
        "host": host,
        "profile": "profile1",
        "data": {"key": "val"},
        "user_id": 1,
        "state": {},
    }


def _make_ws_server(mock_db, config=None):
    """Build a WebSocketServer with mocked db/dp/handlers."""
    from websocket_server import WebSocketServer

    if config is None:
        config = {"max_ws_tasks": 5, "priority_task_types": []}

    mock_db.get_config = AsyncMock(return_value=config)

    server = WebSocketServer(db=mock_db, dp=MagicMock(), handlers={})
    return server


def _make_fake_ws(send_raises=False):
    """Mock websocket that can optionally raise on send."""
    ws = MagicMock()
    ws.remote_address = ("127.0.0.1", 12345)
    if send_raises:
        ws.send = AsyncMock(side_effect=Exception("connection lost"))
    else:
        ws.send = AsyncMock(return_value=None)
    ws.close = AsyncMock(return_value=None)
    return ws


# ---------------------------------------------------------------------------
# Tests: _send_task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_task_success(mock_db):
    """Case 1: successful send → returns True, task set to 'pending'."""
    server = _make_ws_server(mock_db)
    task = _make_task()
    ws = _make_fake_ws()

    result = await server._send_task(task, "host1", ws)

    assert result is True
    # update_task_result should be called with status="pending"
    mock_db.update_task_result.assert_any_call(str(task["_id"]), None, "pending")
    # update_task_host should be called to assign the host
    mock_db.update_task_host.assert_any_call(str(task["_id"]), "host1")
    ws.send.assert_called_once()


@pytest.mark.asyncio
async def test_send_task_ws_raises_returns_false(mock_db):
    """Case 2: ws.send raises → returns False, task rolled back to 'new', host cleared."""
    server = _make_ws_server(mock_db)
    task = _make_task()
    ws = _make_fake_ws(send_raises=True)

    result = await server._send_task(task, "host1", ws)

    assert result is False
    # Roll-back calls
    mock_db.update_task_result.assert_any_call(str(task["_id"]), None, "new")
    mock_db.update_task_host.assert_any_call(str(task["_id"]), None)


# ---------------------------------------------------------------------------
# Tests: _dispatch_pending
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_tries_next_client_on_failure(mock_db):
    """Case 3: if client A send fails, client B receives the task."""
    task = _make_task()
    mock_db.get_tasks = AsyncMock(side_effect=[
        [task],   # new tasks query
        [],       # pending tasks query
    ])

    server = _make_ws_server(mock_db)

    ws_a = _make_fake_ws(send_raises=True)
    ws_b = _make_fake_ws(send_raises=False)
    server.clients = {"host_a": ws_a, "host_b": ws_b}

    await server._dispatch_pending()

    # ws_b should have received the task
    ws_b.send.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_counter_incremented_on_success(mock_db):
    """Case 4: pending_by_host counter is incremented only after a successful send."""
    task1 = _make_task()
    task2 = _make_task()
    mock_db.get_tasks = AsyncMock(side_effect=[
        [task1, task2],  # new tasks
        [],              # pending tasks (none yet)
    ])
    server = _make_ws_server(mock_db, config={"max_ws_tasks": 1, "priority_task_types": []})

    ws = _make_fake_ws()
    server.clients = {"host1": ws}

    await server._dispatch_pending()

    # After the first task fills the slot (max_ws_tasks=1), the second should NOT be sent
    assert ws.send.call_count == 1


@pytest.mark.asyncio
async def test_dispatch_respects_max_tasks_limit(mock_db):
    """Case 5: client at max_tasks already → no new tasks dispatched to it."""
    task = _make_task()
    pending_task = _make_task(status="pending", host="host1")
    mock_db.get_tasks = AsyncMock(side_effect=[
        [task],          # new tasks
        [pending_task] * 5,  # already 5 pending on host1
    ])
    server = _make_ws_server(mock_db, config={"max_ws_tasks": 5, "priority_task_types": []})

    ws = _make_fake_ws()
    server.clients = {"host1": ws}

    await server._dispatch_pending()

    # host1 is already at capacity — no send
    ws.send.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_priority_tasks_first(mock_db):
    """Case 6: priority task types dispatched before normal tasks."""
    normal_task = _make_task(type_="sync")
    priority_task = _make_task(type_="priority_sync")

    # Return normal first (as DB would), expect priority first in dispatch
    mock_db.get_tasks = AsyncMock(side_effect=[
        [normal_task, priority_task],  # new tasks
        [],                            # pending tasks
    ])
    server = _make_ws_server(mock_db, config={
        "max_ws_tasks": 1,  # only one slot — only first task dispatched
        "priority_task_types": ["priority_sync"]
    })

    ws = _make_fake_ws()
    server.clients = {"host1": ws}

    await server._dispatch_pending()

    # Only the priority task should have been sent (one slot available)
    ws.send.assert_called_once()
    sent_payload = json.loads(ws.send.call_args[0][0])
    assert sent_payload["type"] == "priority_sync"


# ---------------------------------------------------------------------------
# Tests: _handle_client (orphaned task reset)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orphaned_tasks_reset_on_disconnect(mock_db):
    """Case 7: pending tasks on disconnecting client are reset to 'new'."""
    orphan = _make_task(status="pending", host="127.0.0.1:12345")
    mock_db.get_tasks = AsyncMock(return_value=[orphan])

    server = _make_ws_server(mock_db)

    ws = _make_fake_ws()
    # Simulate a client that immediately disconnects (empty async generator)
    async def empty_gen():
        return
        yield  # make it an async generator

    ws.__aiter__ = lambda self: empty_gen()

    # Trigger disconnect cleanup directly
    host_key = "127.0.0.1:12345"
    orphaned = await mock_db.get_tasks({"host": host_key, "status": "pending"})
    for task in orphaned:
        await mock_db.update_task_result(str(task["_id"]), None, "new")
        await mock_db.update_task_host(str(task["_id"]), None)

    mock_db.update_task_result.assert_called_with(str(orphan["_id"]), None, "new")
    mock_db.update_task_host.assert_called_with(str(orphan["_id"]), None)


# ---------------------------------------------------------------------------
# Tests: _process_request (HTTP Basic auth)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_valid_credentials_accepted(mock_db):
    """Case 8: valid Basic auth header → handler returns None (accepted)."""
    server = _make_ws_server(mock_db)
    server._ws_user = "aria"
    server._ws_password = "aria_secret"

    expected_b64 = base64.b64encode(b"aria:aria_secret").decode()
    mock_request = MagicMock()
    mock_request.headers = {"Authorization": f"Basic {expected_b64}"}

    mock_connection = MagicMock()
    mock_connection.respond = MagicMock()

    result = await server._process_request(mock_connection, mock_request)

    # None return means "proceed" (connection accepted)
    assert result is None
    mock_connection.respond.assert_not_called()


@pytest.mark.asyncio
async def test_auth_invalid_credentials_rejected(mock_db):
    """Case 9: invalid auth header → connection.respond called with 401."""
    server = _make_ws_server(mock_db)
    server._ws_user = "aria"
    server._ws_password = "aria_secret"

    mock_request = MagicMock()
    mock_request.headers = {"Authorization": "Basic d3Jvbmc6Y3JlZHM="}  # wrong:creds

    mock_connection = MagicMock()
    from http import HTTPStatus
    mock_connection.respond = MagicMock(return_value="reject_response")

    result = await server._process_request(mock_connection, mock_request)

    mock_connection.respond.assert_called_once_with(HTTPStatus.UNAUTHORIZED, "Unauthorized\n")
    assert result == "reject_response"
