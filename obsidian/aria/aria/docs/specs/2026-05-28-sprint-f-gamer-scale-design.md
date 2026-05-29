---
name: sprint-f-gamer-scale-performance
description: Paginated gamer account screen, paginated release selector, N+1 fix in get_open_support_tasks, parallel role resolution, leaderboard TTL cache
type: spec
status: approved
updated: 2026-05-28
version: "1"
---

# Sprint F — Gamer Scale & Performance

> Design approved: 2026-05-28
> Related: [[NEXT]] · [[flows]] · [[data-model]]

---

## Motivation

At 15–20 accounts per gamer the current implementation has two silent failure modes and several performance bottlenecks:

1. `gamer_account` builds a single message containing every account's full credential block. At ~350 chars/account × 17 accounts ≈ 5,900 chars — exceeds Telegram's 4,096-char limit. `safe_wrap` swallows the error; the gamer sees nothing.
2. `gamer_release_account_prompt` renders one inline button per account with no pagination. At 15-20 accounts this is an unusable wall of buttons.
3. `get_open_support_tasks` does N+1 MongoDB queries (one `find_one` per account to join gamer info).
4. `start()` resolves role via three sequential `await db.is_*()` calls.
5. Leaderboard runs a full aggregation on every tap with no caching.

---

## Scope

| # | Feature | Files |
|---|---|---|
| F1 | Paginated gamer account screen (10/page, compact format, inline nav) | `main.py`, `texts.py` |
| F2 | Paginated release account selector (10/page, inline nav) | `main.py` |
| F3 | `get_open_support_tasks` → single `$lookup` aggregation | `mongodb.py` |
| F4 | Parallel role resolution in `start()` via `asyncio.gather` | `main.py` |
| F5 | Leaderboard TTL cache (60s, in-memory) | `mongodb.py` |

---

## F1 — Paginated Gamer Account Screen

### Format

Each account renders as a compact block (proxy format unchanged):

```
✅ *ProfileName* | 12345pt \(\+678\) | Rank 42 | Floor 15
`login@email` / `password`

Proxy:
    Host: `host`
    Port: `port`
    Login: `proxylogin`
    Password: `proxypass`
```

~200 chars per account × 10 = ~2,000 chars. Total message (header + accounts + nav) stays under 3,500 chars comfortably.

### Message structure

```
[Header: wallet address, referral, season balance]

--- Accounts (page X/Y) ---
[10 account blocks]

◀️  X/Y  ▶️  🔄
```

Header (wallet, referral, balance) is static — not paginated. Only the accounts table and page indicator change.

### State and data flow

- FSM state: remains `TelegramState.account` (no new state needed)
- On first load (`gamer_account` handler): build page 0, send message, store `{"account_page": 0}` in FSM context via `state.update_data`
- New callback: `account_page:{n}` registered on `TelegramState.account`
  - `await callback_query.answer("")` first
  - Re-fetch both `gamer` and `accounts` from DB (fresh data — status may have changed between pages)
  - Call `_build_account_page(accounts, gamer, page, config)` → `(text, inline_markup)`
  - `edit_message_text` to update in-place (same pattern as `dashboard_paginate`)
- Nav buttons: `◀️` (if page > 0), `X/Y` (noop → `account_page_noop`), `▶️` (if page < total-1), `🔄` (refresh current page)

### Helper function

```python
async def _build_account_page(accounts, gamer, page, config):
    """Returns (text: str, markup: InlineKeyboardMarkup)"""
    PAGE_SIZE = 10
    total_pages = max(1, (len(accounts) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_accounts = accounts[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    # ... build header, compact account blocks, nav buttons
    # Returns full MarkdownV2 text + InlineKeyboardMarkup
```

### Message cleanup

`gamer_account` uses the existing cleanup pattern:
```python
await utils.add_message_history(db, message)      # track incoming
await utils.clean_messages(bot, db, user_id)       # delete previous
sent = await safe_wrap(lambda: message.answer(...))
await utils.add_message_history(db, sent)          # track outgoing
```

`account_page` callback edits in-place — no new messages sent, no additional cleanup needed.

---

## F2 — Paginated Release Account Selector

### Keyboard layout

10 accounts per page. Each button: `ProfileName (башня: 12345, +678)` — unchanged from current format. Callback data: `release_select:{oid_hex}`.

Nav buttons in a separate row: `◀️  X/Y  ▶️` + existing `↩️ Назад` button always visible.

### State and data flow

- FSM state: `TelegramState.gamer_release_account` (unchanged)
- On first load (`gamer_release_account_prompt`): build page 0, send message
- New callback: `release_page:{n}` registered on `TelegramState.gamer_release_account`
  - `await callback_query.answer("")` first
  - Re-fetch releasable accounts
  - `edit_message_text` with new page's keyboard
- `release_back` callback unchanged

---

## F3 — N+1 Fix in `get_open_support_tasks`

Replace the per-account `find_one` loop with a single aggregation pipeline:

```python
pipeline = [
    {"$match": {"status": {"$in": ["escalated", "pending_release"]}}},
    {"$lookup": {
        "from": "gamers",
        "localField": "gamer_id",
        "foreignField": "_id",
        "as": "gamer_arr"
    }},
    {"$addFields": {"gamer": {"$arrayElemAt": ["$gamer_arr", 0]}}},
    {"$project": {"gamer_arr": 0}},
    {"$sort": {"status": 1}}  # "escalated" < "pending_release" lexically → escalated first
]
result = await self.db.accounts.aggregate(pipeline).to_list(None)
return result
```

Return shape is identical to the current method — each item has a `gamer` key (joined doc or `None`). No changes needed in callers (`_build_dashboard_page`, `dashboard_paginate`).

**Note on sort:** `"escalated"` < `"pending_release"` lexically, so `$sort: {"status": 1}` gives escalated first. Correct.

---

## F4 — Parallel Role Resolution in `start()`

```python
uid = message.from_user.id
is_sa, is_sup, is_gm = await asyncio.gather(
    db.is_superadmin(uid),
    db.is_support(uid),
    db.is_gamer(uid)
)

if is_sa:
    await TelegramState.superadmin_start.set()
    ...
elif is_sup:
    await TelegramState.support_start.set()
    ...
elif is_gm:
    await TelegramState.start.set()
    ...
else:
    # newcomer / invite-only
    ...
```

Import: `import asyncio` at top of `main.py` (verify not already imported).

---

## F5 — Leaderboard TTL Cache

In `mongodb.py`, module-level cache dict:

```python
import time as _time

_leaderboard_cache: dict = {}   # keys: "data", "ts"
LEADERBOARD_TTL_SECONDS = 60
```

In `get_all_gamers_season_points()`:

```python
async def get_all_gamers_season_points(self):
    now = _time.time()
    if _leaderboard_cache.get("ts") and now - _leaderboard_cache["ts"] < LEADERBOARD_TTL_SECONDS:
        return _leaderboard_cache["data"]
    result = await self._run_aggregation_or_existing_logic(...)
    _leaderboard_cache.update({"data": result, "ts": now})
    return result
```

Single-process safe (Motor runs in one event loop). No external dependency.

Cache is per-process — QA and production are isolated naturally.

---

## Testing

New test file: `tests/test_sprint_f.py`

| Test | Covers |
|---|---|
| `test_account_page_builds_correctly` | `_build_account_page` with 25 accounts returns page 0 (10 items), page 1 (10 items), page 2 (5 items) |
| `test_account_page_char_limit` | Each page's text is < 4,000 chars (safety margin below 4,096) |
| `test_account_page_compact_format` | Proxy block format unchanged; header line contains profile, tower points, rank, floor |
| `test_release_page_builds_correctly` | `_build_release_page` with 15 accounts: page 0 has 10 buttons + nav, page 1 has 5 buttons + nav |
| `test_get_open_support_tasks_aggregation` | Aggregation returns gamer joined; escalated items before pending_release |
| `test_start_parallel_role_resolution` | `asyncio.gather` called; superadmin branch taken when is_superadmin=True |
| `test_leaderboard_cache_hit` | Second call within TTL returns same object without DB call |
| `test_leaderboard_cache_miss` | Call after TTL expired re-runs aggregation |

---

## Out of scope

- Sheet sync automation (separate project)
- Per-account drill-down view from paginated account screen
- Leaderboard configurable TTL (hardcoded 60s; can move to `config` collection later)
