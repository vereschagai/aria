# Module: websocket_server.py

[[aria/CONTEXT]] | [[aria/modules/mongodb]] | [[aria/modules/main]]

## Purpose

Runs a WebSocket server inside the aiogram event loop. Accepts connections from `ws_resolver.js` (automation worker), dispatches `tasks` from MongoDB to connected clients, and processes result callbacks — triggering the appropriate Python handler registered per task type.

---

## Class: `WebSocketServer`

### Constructor

```python
WebSocketServer(db: MongoDb, dp, handlers: dict)
```

| Param | Type | Notes |
|---|---|---|
| `db` | `MongoDb` | Used for all task DB reads/writes |
| `dp` | `Dispatcher` | aiogram dispatcher — unused currently, reserved for future bot-triggered tasks |
| `handlers` | `dict[str, coroutine]` | Map of task type → async result handler. E.g. `{"check_leaderboard_points": on_check_leaderboard_points}` |

**Init side effects:**
- `self._dispatch_lock = asyncio.Lock()` — serialises concurrent dispatch calls
- `self._ws_user`, `self._ws_password` — read from `WS_USER` / `WS_PASSWORD` env vars (defaults: `aria` / `aria_secret`)

---

### `serve(host=None, port=None)`

Starts the WebSocket server. Reads `WS_HOST` (default `0.0.0.0`) and `WS_PORT` (default `8765`) from env when no args passed. Binds to all interfaces by default — accessible on loopback, LAN, and public IP simultaneously.

`websockets.serve` is configured with:
- `process_request=self._process_request` — Basic Auth gate
- `ping_interval=30`, `ping_timeout=10` — dead connection detection
- `max_size=10MB` — prevents oversized payloads

Called from `main.py` via `asyncio.run_coroutine_threadsafe(ws_server.serve(), dp.loop)`.

---

### `_process_request(connection, request)`

HTTP 401 Basic Auth enforced before the WebSocket handshake. Checks `Authorization: Basic <base64(user:password)>` header. Returns `connection.respond(HTTPStatus.UNAUTHORIZED, ...)` on mismatch; returns `None` (implicit accept) on success.

**Env vars:** `WS_USER`, `WS_PASSWORD` (must match `WS_LOGIN`, `WS_PASSWORD` in `ws_resolver.js`).

---

### `create_task(user_id, type, task_state, profile, data, deadline=None)`

Creates a new task document in MongoDB (`status="new"`) and immediately calls `_dispatch_pending()` to send it to a connected client if one is available.

**Task document schema:**

```json
{
  "host": null,
  "user_id": null,
  "type": "check_leaderboard_points",
  "state": {},
  "profile": "<octo_profile_name>",
  "data": {
    "account": {
      "profile": "...",
      "login": "...",
      "password": "...",
      "proxy": {}
    }
  },
  "status": "new",
  "created_at": "<utc>",
  "updated_at": "<utc>",
  "result": null
}
```

**Security note:** `data` must never contain MetaMask seed phrases, wallet passwords, or private keys. The JS worker fetches those directly from Google Sheets via `getAriaAccountMetamask()`.

---

### `_handle_client(websocket, path="")`

Called for each new WebSocket connection. 

- Derives `host_key = "{client_ip}:{client_port}"` — unique per connection, changes on reconnect (correct behaviour).
- Registers client in `self.clients`.
- Immediately calls `_dispatch_pending()` to push any queued tasks.
- Reads incoming messages in a loop, parsing JSON and passing to `_on_result()`.
- On disconnect (`finally`): removes from `self.clients`, resets all `pending` tasks assigned to this host back to `status="new"` so they are re-dispatched to the next available client.

---

### `_dispatch_pending()`

Acquires `self._dispatch_lock` (prevents concurrent dispatch races from `create_task`, `_handle_client`, and `_on_result` all calling this simultaneously).

**Algorithm:**
1. Fetch config: `max_ws_tasks` (default 5), `priority_task_types` (default `["check_leaderboard_points"]`)
2. Fetch all `status="new"` tasks
3. Sort: priority types first, then FIFO by creation order
4. Fetch all `status="pending"` tasks once → build `pending_by_host` counter in memory (avoids N+1 DB queries per client per task)
5. For each queued task: iterate clients in order
   - If client has capacity (`pending < max_tasks`) and `_send_task` succeeds → increment counter, mark dispatched, `break` inner loop (move to next task)
   - If `_send_task` fails → **continue to next client** (do not abort the pass — a flaky client A will fall through to healthy client B)
6. `break` outer loop only if no client accepted the task (all at capacity or all sends failed)

The `break` is inside the send-success block. A failed send to one client tries the next — the entire dispatch pass does not abort on a single connection error.

### `_send_task(task, host_key, ws)`

Sets task `status="pending"`, sets `host=host_key` in DB, sends JSON payload over WebSocket.

**Payload sent to JS worker:**
```json
{
  "task_id": "<mongo_oid_hex>",
  "type": "check_leaderboard_points",
  "profile": "<octo_profile_name>",
  "data": { "account": { ... } }
}
```

Rolls back to `status="new"`, `host=null` if `ws.send()` throws.

---

### `_on_result(msg, host_key)`

Handles result message from JS worker. Expected shape:
```json
{
  "task_id": "<oid_hex>",
  "status": "done" | "error" | "pending",
  "data": { ... }
}
```

Updates task in DB via `update_task_result()`, then calls the registered handler for the task type. Calls `_dispatch_pending()` after the handler returns to fill the freed slot.

---

## Connection Key Strategy

`host_key = "{client_ip}:{client_port}"` — identifies a single TCP connection. On reconnect, the port changes so the old orphaned tasks are cleaned up and the new connection starts fresh. This correctly handles:
- Multiple machines connecting simultaneously (different IPs)
- Single machine reconnecting after crash (new port, clean state)
- **Does not support:** multiple workers on the same machine on the same port (impossible by definition)

---

## Local Network Access

The server binds to `0.0.0.0` by default — no extra config needed on the server side. For the JS worker (`ws_resolver.js`) to connect from a different machine on the same LAN:

```
WS_HOST=<server_lan_ip>   # e.g. 192.168.1.100
WS_PORT=8765
WS_PROTOCOL=ws
WS_LOGIN=aria
WS_PASSWORD=aria_secret
```

The Python server's `WS_HOST` should remain `0.0.0.0` (listen on all interfaces). Firewall must allow port 8765 on the LAN interface.

---

## Task Statuses

| Status | Meaning |
|---|---|
| `new` | Created, not yet dispatched |
| `pending` | Sent to a JS worker, awaiting result |
| `done` | Completed successfully |
| `error` | JS worker reported an error |

---

## Registered Task Types (current)

| Type | Handler | Trigger |
|---|---|---|
| `check_leaderboard_points` | `on_check_leaderboard_points` in `main.py` | Daily cron at 02:00 UTC |

---

## See Also

- [[aria/flows/points-check]] — full flow diagram for the daily points check
- [[aria/modules/mongodb]] — `get_tasks`, `create_task`, `update_task_result`, `update_task_host`
- [[aria/DECISIONS]] — ADR: WebSocket task system replaces sheet-polling; ADR: sensitive data stays on JS side
