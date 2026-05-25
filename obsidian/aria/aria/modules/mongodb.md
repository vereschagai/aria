# Module: mongodb.py

**Type:** Database layer  
**Lines:** 443  
**Class:** `MongoDb`  
**Driver:** motor 3.0.0 (async MongoDB)

## Responsibilities

All database operations. No business logic beyond query construction. Called from [[modules/main]], [[modules/operator_controller]], [[modules/sheet_synchonizer]], [[modules/progress_monitor]], [[modules/mongo_scripts]].

## Collections

| Collection | Purpose |
|---|---|
| `accounts` | Game accounts with progress history and ownership |
| `gamers` | Telegram users with gamer role |
| `admins` | Admin-role users |
| `operators` | Operator-role users |
| `support` | Support-role users |
| `config` | Bot configuration (single document) |
| `messages` | Tracked message IDs for cleanup |

## Key Methods

### Assignment and Eligibility

```python
check_assignment_eligibility(gamer_object_id, config) → (bool, str)
```
Two conditions must both pass:
1. `count_gamer_accounts()` < `config.max_accounts_per_gamer`
2. For every active account: `progress_history[-1].gamer_id == this_gamer` AND `delta >= min_progress_points`

Accounts with empty `progress_history` are skipped (newly assigned — no data yet).
`pending_release` accounts count toward slot limit but are excluded from progress check.
Escalated accounts count toward slot limit but do NOT block eligibility (see [[DECISIONS]]).

```python
pickup_account(gamer_object_id) → account_doc | None
```
Priority 1: accounts where gamer appears in any `ownership_history[].gamer_id`, sorted desc by `tower.points`.  
Priority 2: released accounts whose last owner has `season_picked_up != True`, sorted desc by `tower.points`.  
Atomic `findOneAndUpdate` with `status == "released"` guard prevents race conditions.

```python
mark_gamer_season_active(gamer_object_id)
```
Sets `season_picked_up: True` on first pickup. Enables P2 query logic.

### Release

```python
release_account(profile, status, released_at)
```
Closes open `ownership_history` entry (`released_at = now`), clears `gamer_id`, `$unset`s `pending_proof` and `release_request` (sparse fields).

### Progress and Season Points

```python
get_gamer_season_points(gamer_object_id) → int
get_all_gamers_season_points() → list  # sorted desc, used for leaderboard
```
Aggregation pipeline: unwind `progress_history`, filter `delta > 0` AND `gamer_id == oid`, sum.

### Indexes (via `ensure_indexes()`)

- `accounts`: `profile` (unique), `gamer_id`, `status`, `last_progress_at`, `tower.points` (desc), `progress_history.gamer_id`, `ownership_history.gamer_id`
- `gamers`: `id` (unique), `username` (sparse), `referral`, `season_picked_up` (sparse)
- `admins`: `(id, superadmin)` compound
- `operators`, `support`: `id` (unique)
- `messages`: `id` (unique)

## Account Document Schema

```
{
  profile: str,               // Octo Browser profile name (primary key)
  login: str,
  password: str,
  proxy: str,
  status: "released" | "active" | "escalated" | "pending_release" | "inactive",
  gamer_id: ObjectId | null,
  tower: { points: int },
  ownership_history: [{ gamer_id, assigned_at, released_at }],
  progress_history: [{ synced_at, tower_points, delta, gamer_id }],
  last_progress_at: datetime,
  last_synced_at: datetime,
  last_notified_day: int,     // ordinal date for deduplication
  escalated_at: datetime,
  pending_proof: int,         // sparse — message_id
  release_request: bool       // sparse
}
```

## Gamer Document Schema

```
{
  id: int,                    // Telegram user ID
  username: str,
  referral: str,
  address: str,               // EVM wallet
  season_picked_up: bool      // set on first pickup
}
```

## Dependencies

- motor (async MongoDB driver)
- bson (ObjectId)
