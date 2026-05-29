# Season 4 System Design

ADR for the Season 4 account assignment model. Records decisions made in Cowork; implementation follows from this document.

---

## Problem

Season 3 assignment flow required operator manual intervention:

1. Gamer taps "Запросить аккаунт" → bot notifies all operators
2. Operator updates Google Sheet manually
3. Superadmin runs sync → account is assigned

This created a bottleneck: gamer wait times depended on operator availability, operators were spammed with requests, and the process was error-prone.

---

## Decision: Instant auto-assign

Replace the manual request flow with an automated pickup that assigns the best available account instantly.

**New flow:**
1. Gamer taps "🎮 Взять аккаунт"
2. Eligibility checked — if not eligible, show reason
3. `pickup_account()` finds and atomically assigns the best available account
4. Gamer receives credentials immediately in chat

No operator notification. No waiting. No intermediate FSM state.

---

## Eligibility check changes

Season 3 had three conditions:
1. Slot count < max
2. Active accounts meet progress threshold
3. Pool congestion: previously-released accounts in pool < 5

**Season 4 removes condition 3** (pool congestion cap). The pool is managed implicitly by the Priority 1/2 pickup order — an active gamer always gets their own accounts back first.

**Season 4 adds gamer_id ownership guard to condition 2:** the last progress entry must belong to this gamer (`progress_history[-1].gamer_id == gamer._id`). This prevents a gamer from picking up a new account on the strength of a previous owner's progress sync that happened before the assignment was reflected in the sheet.

---

## Pickup priority

Available accounts (`status == "released"`) are tried in this order, with atomic `findOneAndUpdate` preventing double-claims:

**Priority 1** — Accounts this gamer has previously owned (any entry in `ownership_history.gamer_id`). Sorted descending by `tower.points` (higher-value accounts first — returning gamers resume where they left off).

**Priority 2** — Remaining released accounts where the last owner is inactive this season (`season_picked_up` absent or not `true`) or there is no previous owner. Sorted descending by `tower.points`.

Accounts whose last owner is still active this season are excluded from Priority 2 — they are reserved for that owner's Priority 1 pickup.

---

## `season_picked_up` flag

Added to `gamers` collection. Set to `true` on first `pickup_account()` call this season (idempotent via `mark_gamer_season_active()`). Absent = falsy.

Used exclusively by `pickup_account()` to distinguish active-this-season owners (exclude from P2) from inactive ones (include in P2).

**Reset between seasons:** `migration_season5.py` (future) will `$unset` this field for all gamers as part of the next season reset.

---

## Data model changes from Season 3

| Field | Season 3 | Season 4 |
|---|---|---|
| `accounts.season3_start_points` | Present — seed value for delta calculation | **Removed** — seed value stored in `progress_history[0]` instead |
| `accounts.available_for_pickup` | `true` when `status == "released"` | **Removed** — availability is `status == "released"` (no redundant flag) |
| `accounts.ownership_history[].gamer_username` | Stored on each entry | **Removed** — username resolved on demand from `gamers` collection |
| `accounts.progress_history[0]` | First real sync entry | **Seed entry** added by migration: `{synced_at, tower_points: start_points, delta: start_points, gamer_id: null}` |
| `gamers.season_picked_up` | Absent | **Added** — bool, sparse, set on first pickup |

---

## Migration (`migration_season4.py`)

Run once on production via SSH tunnel before deploying Season 4 bot. Idempotent — skips accounts that do not have `season3_start_points` (already migrated).

For each account with `season3_start_points`:

1. Build seed `progress_history` entry: `{synced_at: now, tower_points: season3_start_points, delta: season3_start_points, gamer_id: current_gamer_id}`
2. If account has an open `ownership_history` entry (`released_at: null`): close it with `released_at: now`
3. `$set`: `status = "released"`, `gamer_id = null`, prepend seed to `progress_history`, rewrite closed `ownership_history` (strip `gamer_username` from all entries)
4. `$unset`: `season3_start_points`, `available_for_pickup`, `gamer` (Season 1 legacy string), `pending_proof`, `release_request`

**Verification before bot deploy:**
```js
// Should return 0 after migration
db.accounts.countDocuments({ season3_start_points: { $exists: true } })

// Spot-check a released account
db.accounts.findOne({ status: "released" })
// → has progress_history[0] with delta == tower_points
// → no season3_start_points field
// → no available_for_pickup field
```

---

## Deployment order

```
1. SSH tunnel to production
2. python3 migration_season4.py
3. Verify in mongo shell (see above)
4. npm run deploy-prod
5. npm run logs-prod  (check bot starts cleanly)
6. Test pickup flow manually with one gamer account
```

---

## Removed code

| Item | Location |
|---|---|
| `count_gamer_available_releases()` | `mongodb.py` |
| Pool congestion check (condition 3) | `mongodb.py::check_assignment_eligibility` |
| Operator notification loop | `main.py::gamer_request_account` (handler renamed to `gamer_pickup_account`) |
| `gamer_request_account_eligible` text | `texts.py` |
| `operator_account_request` text | `texts.py` |
| `request_account` FSM state | `state.py` |
| `available_for_pickup` index | `mongodb.py::ensure_indexes` |
| `season3_start_points` fallback in synchonizer | `sheet_synchonizer.py` |
| `gamer_username` on ownership_history entries | `mongodb.py`, `migration_season4.py` |
