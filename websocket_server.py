import asyncio
import base64
import json
import logging
import os
from datetime import datetime
from http import HTTPStatus

import websockets
from websockets.exceptions import ConnectionClosed

from mongodb import MongoDb


class WebSocketServer:
    def __init__(self, db: MongoDb, dp, handlers: dict):
        self.db = db
        self.dp = dp
        self.handlers = handlers
        self.clients = {}  # host_key -> websocket
        self._dispatch_lock = asyncio.Lock()
        self._ws_user = os.environ.get("WS_USER", "aria")
        self._ws_password = os.environ.get("WS_PASSWORD", "aria_secret")

    async def serve(self, host=None, port=None):
        host = host or os.environ.get("WS_HOST", "0.0.0.0")
        port = port or int(os.environ.get("WS_PORT", "8765"))
        logging.info(f"[WS] Starting WebSocket server on {host}:{port}")
        async with websockets.serve(
            self._handle_client, host, port,
            process_request=self._process_request,
            ping_interval=30,
            ping_timeout=10,
            max_size=10 * 2**20,  # 10 MB
        ):
            await asyncio.Future()  # run forever

    async def _process_request(self, connection, request):
        expected = base64.b64encode(
            f"{self._ws_user}:{self._ws_password}".encode()
        ).decode()
        auth = request.headers.get("Authorization", "")
        if auth != f"Basic {expected}":
            return connection.respond(HTTPStatus.UNAUTHORIZED, "Unauthorized\n")

    async def create_task(self, user_id, type: str, task_state: dict, profile: str, data: dict, deadline=None):
        task = {
            "host": None,
            "user_id": user_id,
            "type": type,
            "state": task_state,
            "profile": profile,
            "data": data,
            "status": "new",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "result": None,
        }
        if deadline is not None:
            task["deadline"] = deadline
        await self.db.create_task(task)
        await self._dispatch_pending()

    async def _handle_client(self, websocket, path=""):
        host_key = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        self.clients[host_key] = websocket
        logging.info(f"[WS] Client connected: {host_key}")

        try:
            await self._dispatch_pending()
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                    await self._on_result(msg, host_key)
                except json.JSONDecodeError:
                    logging.warning(f"[WS] Bad JSON from {host_key}: {raw[:200]}")
                except Exception as e:
                    logging.error(f"[WS] Error handling message from {host_key}: {e}")
        except ConnectionClosed:
            pass
        finally:
            self.clients.pop(host_key, None)
            logging.info(f"[WS] Client disconnected: {host_key}")
            # Reset any tasks left pending on this client back to "new" so they get re-dispatched
            orphaned = await self.db.get_tasks({"host": host_key, "status": "pending"})
            for task in orphaned:
                await self.db.update_task_result(str(task["_id"]), None, "new")
                await self.db.update_task_host(str(task["_id"]), None)

    async def _dispatch_pending(self):
        async with self._dispatch_lock:
            if not self.clients:
                return

            config = await self.db.get_config()
            max_tasks = config.get("max_ws_tasks", 5) if config else 5
            priority_types = config.get("priority_task_types", []) if config else []

            new_tasks = await self.db.get_tasks({"status": "new"})
            if not new_tasks:
                return

            # Priority types first, then FIFO by created_at
            priority = [t for t in new_tasks if t["type"] in priority_types]
            normal = [t for t in new_tasks if t["type"] not in priority_types]
            queue = priority + normal

            # Fetch all pending tasks once — avoids N+1 DB queries in the dispatch loop
            pending_tasks = await self.db.get_tasks({"status": "pending"})
            pending_by_host = {}
            for t in pending_tasks:
                h = t.get("host") or ""
                pending_by_host[h] = pending_by_host.get(h, 0) + 1

            for task in queue:
                dispatched = False
                for host_key, ws in list(self.clients.items()):
                    if pending_by_host.get(host_key, 0) < max_tasks:
                        if await self._send_task(task, host_key, ws):
                            pending_by_host[host_key] = pending_by_host.get(host_key, 0) + 1
                            dispatched = True
                            break  # sent successfully — move to next task
                        # send failed — continue to next client
                if not dispatched:
                    break  # all clients at capacity

    async def _send_task(self, task: dict, host_key: str, ws) -> bool:
        task_id = str(task["_id"])
        await self.db.update_task_host(task_id, host_key)
        await self.db.update_task_result(task_id, None, "pending")

        payload = {
            "task_id": task_id,
            "type": task["type"],
            "profile": task["profile"],
            "data": task["data"],
        }
        try:
            await ws.send(json.dumps(payload))
            logging.info(f"[WS] Dispatched task {task_id} ({task['type']}) to {host_key}")
            return True
        except Exception as e:
            logging.error(f"[WS] Failed to send task {task_id} to {host_key}: {e}")
            # Roll back so the task can be re-dispatched
            await self.db.update_task_result(task_id, None, "new")
            await self.db.update_task_host(task_id, None)
            return False

    async def _on_result(self, msg: dict, host_key: str):
        task_id = msg.get("task_id")
        status = msg.get("status")
        result_data = msg.get("data", {})

        if not task_id or not status:
            logging.warning(f"[WS] Malformed result from {host_key}: missing task_id or status")
            return

        task = await self.db.get_task(task_id)
        if not task:
            logging.error(f"[WS] Received result for unknown task {task_id}")
            return

        await self.db.update_task_result(task_id, result_data, status)

        handler = self.handlers.get(task["type"])
        if handler:
            try:
                await handler(
                    task.get("user_id"),
                    task_id,
                    host_key,
                    task.get("state", {}),
                    task.get("data", {}),
                    result_data,
                    status,
                )
            except Exception as e:
                logging.error(f"[WS] Handler error for task {task_id} ({task['type']}): {e}")

        await self._dispatch_pending()
