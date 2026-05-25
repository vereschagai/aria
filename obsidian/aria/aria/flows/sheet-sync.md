# Flow: Sheet Sync

**Trigger:** Superadmin presses "🔄 Синхронизация" button in `TelegramState.superadmin_start`  
**Actor:** Superadmin (manual trigger); future: automated via Octo+Puppeteer pipeline  
**Handler:** `superadmin_grab_accounts()` — main.py line 184

## Steps

```
1. Superadmin presses sync button
        ↓
2. superadmin_grab_accounts()
   → synchonizer.grab_accounts()  [awaited — blocks handler until complete]
        ↓
3. google_api.get_accounts()  ← SYNCHRONOUS HTTP call, blocks asyncio event loop
   Returns raw rows from Accounts!A2:AQ
        ↓
4. db.get_config() → read min_progress_points (default 50)
        ↓
5. For each sheet row:
   Skip if: profile empty, row < 6 cols, col[5] == "#N/A" (inactive), col[3] == "#N/A" (no proxy)

   __make_db_account(row):
     profile = col[0]
     login = col[1], password = col[2]
     proxy = col[3] (split host:port:login:pass into dict)
     tower = __parse_tower(col[-1])        ← rightmost column = latest daily sync
     tp_start = __parse_tower(col[7])      ← TP Start baseline

   __parse_tower(raw):
     format: "points;rank;floor"
     handles: NaN;NaN;NaN, empty string, float, IndexError → returns {points:0, rank:0, floor:0}

   db.get_account(profile):
        ↓
   NEW account:
     seed progress_history[0] = {
       synced_at: now, tower_points: tp_start.points,
       delta: tp_start.points, gamer_id: None
     }
     status = "released", gamer_id = None, ownership_history = []
     db.accounts.insert_one(account_data)

   EXISTING account:
     delta = new_tower_points - progress_history[-1].tower_points
     (if progress_history empty: delta = 0, prev_points = new_tower_points)
     update_fields = {profile, login, password, proxy, tower, last_synced_at}
     if delta >= min_progress_points: also set last_progress_at = now
     db.accounts.update_one($set + $push progress_history entry)
        ↓
6. progress_monitor.check_all()  [see flows/inactivity-escalation]
        ↓
7. send texts.admin_grab_account_done + markups.superadmin_start
```

## Key Invariants

- `gamer` column (col[6]) is **never read** — Option C (see [[DECISIONS]])
- Delta always uses `progress_history[-1].tower_points` as baseline — no special-casing for start points
- Points synced while account is in pool (`gamer_id: null`) have `delta` attributed to `gamer_id: None`

## Parallel External Pipeline (not in this repo)

A Windows laptop runs Octo Browser profiles + Puppeteer scripts daily:
1. Scrapes live tower points per account from the game website
2. Writes results to Google Sheets columns I+ (col index 8+), one column per day
3. This is the upstream data source for this sync

## Edge Cases

- Google Sheets HTTP call is synchronous — blocks the event loop; no timeout
- If a proxy string doesn't split into exactly 4 parts, `proxy` is stored as `{}`
- Any exception inside the loop is not caught per-row; an error mid-loop aborts remaining accounts for that sync pass (caught by the global error handler in main.py)
- `last_notified_day` deduplication in progress_monitor prevents double-warning on same sync day

## Modules

- [[modules/main]] — trigger handler
- [[modules/sheet_synchonizer]] — core sync logic
- [[modules/google_api]] — `get_accounts()` Sheets API call
- [[modules/mongodb]] — `get_config`, `get_account`, `put_account`, `push_progress_entry`
- [[modules/progress_monitor]] — `check_all()` called after all updates
- [[modules/texts]] — `admin_grab_account_done`
