# Flow: Daily Points Check (WebSocket)

[[aria/CONTEXT]] | [[aria/modules/websocket_server]] | [[aria/flows/sheet-sync]]

## Overview

Replaces the old sheet-polling tower points load. Runs automatically every day at 02:00 UTC via aiocron. For each active, assigned account: creates a `check_leaderboard_points` task in MongoDB, dispatches it to the connected `ws_resolver.js` automation worker, which runs browser automation to scrape live tower points from `access.playariagame.com`. Results are processed back in Python to update `progress_history` and trigger inactivity checks.

---

## Trigger

```python
@aiocron.crontab('0 2 * * *')
async def daily_points_check():
```

Runs inside the aiogram event loop. Scheduled via aiocron inside `main.py`.

---

## Step 1 — Duplicate Guard

```python
existing_tasks = await db.get_tasks({
    "type": "check_leaderboard_points",
    "status": {"$in": ["new", "pending"]},
})
existing_profiles = {t["profile"] for t in existing_tasks}
```

Skips accounts that already have a live task from a previous batch (e.g. if cron fires twice or a prior batch is still processing).

---

## Step 2 — Account Selection

```python
accounts = await db.get_accounts({"status": "active", "gamer_id": {"$ne": None}})
```

Only actively assigned accounts run the check. Released or escalated accounts are skipped.

---

## Step 3 — Task Creation

For each eligible account, `ws_server.create_task()` is called with:

```python
data = {
    "account": {
        "profile": account["profile"],   # Octo profile name
        "login": account["login"],        # Aria game login
        "password": account["password"],  # Aria game password
        "proxy": account["proxy"],        # Proxy config dict
    }
}
```

**No sensitive data in payload.** MetaMask seed, wallet password, and address are fetched by the JS worker directly from Google Sheets.

---

## Step 4 — WebSocket Dispatch

`WebSocketServer._dispatch_pending()` picks up `status="new"` tasks and sends them to connected `ws_resolver.js` workers (up to `max_ws_tasks` concurrent per worker, default 5). Tasks are prioritised: `check_leaderboard_points` is a priority type.

Payload sent over WebSocket:
```json
{
  "task_id": "<mongo_oid_hex>",
  "type": "check_leaderboard_points",
  "profile": "<profile>",
  "data": { "account": { ... } }
}
```

---

## Step 5 — JS Worker Execution (`automation/scripts/aria.js`)

`wsCheckLeaderboardPoints(profile, profileName, data, updateStatus)`:

1. Calls `getAriaAccountMetamask(profileName)` — reads Aria Google Sheet (`A2:AQ`) to fetch:
   - `seed` (col E) — MetaMask seed phrase
   - `address` (col G) — expected wallet address
   - `walletPassword` (col M) — MetaMask unlock password
   - Results are cached per profileName for 5 minutes

2. If `seed` is present: calls `createMetamaskWallet(profile, profileName, walletPassword, seed)` — ensures MetaMask is set up and unlocked in the Octo browser profile

3. If `address` is present: verifies `wallet.address.toLowerCase() === address.toLowerCase()` — throws `'Metamask address mismatch!'` on mismatch

4. Calls `checkLeaderboardPoints(profile, profileName, walletPassword)` — navigates to game site, reads tower rank tab, returns:
   ```json
   {
     "points": { "points": 1234, "rank": 5 },
     "tower": { "points": 567, "rank": 12, "floor": 8 }
   }
   ```

**Prerequisite:** `ws_resolver.js` must be started with `INCLUDE_METAMASK=true` so `METAMASK_PATH` is resolved at startup.

---

## Step 6 — Result Callback

`ws_resolver.js` sends back:
```json
{
  "task_id": "<oid_hex>",
  "status": "done",
  "data": { "result": { "points": {...}, "tower": {...} } }
}
```

`WebSocketServer._on_result()` updates the task in DB and calls `on_check_leaderboard_points()`.

---

## Step 7 — Python Result Handler (`main.py`)

`on_check_leaderboard_points(user_id, task_id, host, task_state, task_data, result_data, status)`:

1. If `status != "done"` → logs warning and returns (no DB update for partial/error results)

2. Extracts `tower_points`, `tower_rank`, `tower_floor` from `result_data.result.tower`

3. Computes `delta = tower_points - history[-1].tower_points` (or 0 if no history)

4. Pushes `progress_history` entry:
   ```json
   {
     "synced_at": "<utc>",
     "tower_points": 567,
     "tower_rank": 12,
     "tower_floor": 8,
     "delta": 42,
     "gamer_id": "<gamer_oid>"
   }
   ```

5. Updates `account.tower` embedded doc: `{points, rank, floor}`

6. Updates `last_progress_at` if `delta > 0`

7. Calls `progress_monitor.check_account(updated_account)` — triggers inactivity logic immediately after each result, not just after batch completion

---

## Error Cases

| Scenario | Behaviour |
|---|---|
| Worker disconnects mid-task | Orphaned `pending` tasks reset to `new` on disconnect; re-dispatched to next connection |
| JS throws MetaMask mismatch | Task returns `status="error"` with error string; Python handler logs warning |
| JS throws any other error | Same — `status="error"`, logged |
| Account has no active worker | Task stays `status="new"` until a worker connects |
| Profile not in sheet (no MM data) | `seed=""`, wallet init skipped, `checkLeaderboardPoints` runs with empty password |

---

## Related

- [[aria/modules/websocket_server]] — server implementation
- [[aria/flows/sheet-sync]] — replaced as the source of tower points
- [[aria/modules/progress_monitor]] — called per-account after each result
- [[aria/DECISIONS]] — ADR: WebSocket task system; ADR: sensitive data stays on JS side
