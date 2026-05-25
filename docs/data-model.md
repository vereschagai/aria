# Data Model

MongoDB database: `aria` (production) / `aria_qa` (QA).
FSM state is stored in a separate `fsm` collection managed automatically by aiogram's `MongoStorage`.

All collections are accessed exclusively through `MongoDb` in `mongodb.py`. Never write to the database outside that class.

---

## `admin`

Stores both superadmins and regular admins. The `superadmin` boolean distinguishes them.

```json
{
  "_id": "<ObjectId>",
  "id": 208809955,
  "username": "telegramhandle",
  "phone": "+7...",
  "superadmin": true
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | int | Telegram user ID |
| `username` | string | Telegram @handle (no @) |
| `phone` | string | From Telegram contact share |
| `superadmin` | bool | `true` = superadmin, `false` = admin |

**Indexes:** `(id, superadmin)` compound.

---

## `operators`

```json
{
  "_id": "<ObjectId>",
  "id": 123456789,
  "phone": "+7..."
}
```

**Index:** `id` unique.

---

## `support`

Managed identically to operators. Added/removed by admin or superadmin via phone contact share.

```json
{
  "_id": "<ObjectId>",
  "id": 123456789,
  "phone": "+7..."
}
```

**Index:** `id` unique.

All support users receive every escalation and release-request notification simultaneously. First one to press the inline button owns the case; the handler checks `status` before acting so double-taps are safe.

---

## `gamers`

One document per gamer. Created on first `/start` with a valid referral link.

```json
{
  "_id": "<ObjectId>",
  "id": 123456789,
  "username": "telegramhandle",
  "referral": 987654321,
  "referral_name": "handle",
  "address": "0xABC...",
  "season_picked_up": true
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | int | Telegram user ID |
| `username` | string | Telegram @handle (no @) |
| `referral` | int \| null | Telegram ID of referrer |
| `referral_name` | string | Temporary — referrer username before their ID is resolved |
| `address` | string \| null | BSC wallet address (nullable until set by gamer) |
| `season_picked_up` | bool \| absent | Set to `true` on first `pickup_account()` call this season. Absent = falsy. Used by `pickup_account()` to identify previous owners who are inactive this season (priority-2 reassignment candidates). |

**Indexes:** `id` unique, `username` sparse, `referral`, `season_picked_up` sparse.

**Season 3 score** is computed on-the-fly from `accounts.progress_history` — not stored on the gamer document.

---

## `accounts`

One document per game account. Created/updated by `GoogleSheetSynchonizer.grab_accounts()`.

**Critical invariant:** `gamer_id`, `ownership_history`, and all ownership-related fields are **never written by the synchonizer**. Assignment is DB-only (Option C). The synchonizer only writes: `profile`, `login`, `password`, `proxy`, `tower`, `last_synced_at`, `last_progress_at`, and appends to `progress_history`.

### Full schema

```json
{
  "_id": "<ObjectId>",

  "profile": "ProfileName",
  "login": "email@example.com",
  "password": "secret",
  "proxy": {
    "host": "1.2.3.4",
    "port": 8080,
    "login": "proxyuser",
    "password": "proxypass"
  },

  "tower": {
    "points": 1400,
    "rank": 10,
    "floor": 5
  },

  "gamer_id": "<ObjectId | null>",

  "ownership_history": [
    {
      "gamer_id": "<ObjectId>",
      "assigned_at": "<ISODate>",
      "released_at": "<ISODate | null>"
    }
  ],

  "progress_history": [
    {
      "synced_at": "<ISODate>",
      "tower_points": 1200,
      "delta": 200,
      "gamer_id": "<ObjectId | null>"
    }
  ],

  "last_progress_at": "<ISODate | null>",
  "last_synced_at": "<ISODate | null>",
  "last_notified_day": "<int | null>",

  "status": "active",
  "escalated_at": "<ISODate | null>",

  "pending_proof": {
    "submitted_at": "<ISODate>",
    "message_id": 111,
    "chat_id": 123456789
  },

  "release_request": {
    "type": "on_demand",
    "requested_at": "<ISODate>",
    "gamer_id": "<ObjectId>"
  }
}
```

> `pending_proof` and `release_request` are **sparse** — only present when relevant. Both are `$unset` (fully removed) when `release_account()` is called.

```json
```

### Field reference

| Field | Type | Notes |
|---|---|---|
| `profile` | string | Unique identity key; matches Google Sheet col 0 |
| `login` | string | Game account email |
| `password` | string | Game account password |
| `proxy` | object | `{host, port, login, password}` or `{}` if missing |
| `tower` | object | Latest `{points, rank, floor}` from the most recent daily sync column |
| `gamer_id` | ObjectId \| null | Current owner's `_id` from `gamers` collection |
| `ownership_history` | array | Full chain of all owners. Open entry has `released_at: null`. No `gamer_username` — username is resolved on demand. |
| `progress_history` | array | Append-only. One entry per sync, plus seed entry at S3/S4 start. Never overwritten. `progress_history[0]` for Season 4 accounts is the seed entry with delta = start_points, gamer_id = null. |
| `progress_history[].delta` | int | `current_tower_points - previous_tower_points`. Can be negative (game resets). |
| `progress_history[].gamer_id` | ObjectId \| null | Snapshot of who owned the account at sync time. |
| `last_progress_at` | ISODate \| null | Timestamp of last sync where `delta >= min_progress_points`. |
| `last_synced_at` | ISODate \| null | Timestamp of last sync regardless of progress. |
| `last_notified_day` | int \| null | `date.toordinal()` of last inactivity notification. Deduplicates to one notification per calendar day per account. |
| `status` | string | See status lifecycle below. |
| `escalated_at` | ISODate \| null | Set when transitioning to `"escalated"`. |
| `pending_proof` | object \| absent | Sparse. Gamer-submitted proof message (Telegram message ID + chat ID for forwarding). `$unset` on `release_account()`. |
| `release_request` | object \| absent | Sparse. Set when `status == "pending_release"`; `$unset` on support decision. |

### Account status lifecycle

```
                      1+ days inactive
  active ─────────────────────────────▶ escalated
    │                                       │
    │ gamer requests release                │ support: progress possible
    ▼                                       ▼
pending_release                          released  ◀─── support: progress possible
    │                                       (open for pickup_account())
    │ support: approve
    ▼
  released

  pending_release ──▶ active   (support: deny)
  escalated       ──▶ inactive (support: no progress possible)
```

| Status | `gamer_id` | Open for pickup | Inactivity checks |
|---|---|---|---|
| `active` | set | ❌ | ✅ |
| `escalated` | set (until decision) | ❌ | ❌ |
| `pending_release` | set (until decision) | ❌ | ❌ |
| `released` | null | ✅ | ❌ |
| `inactive` | null | ❌ | ❌ |

### Indexes

```
profile                              unique
gamer_id
status
last_progress_at
(tower.points, DESCENDING)
(progress_history.gamer_id, ASCENDING)
```

---

## `config`

Single document. Read via `db.get_config()`. Written by superadmin via ⚙️ Конфигурация.
Bootstrapped on startup from `config.py` defaults — only missing fields are added, existing values are never overwritten.

```json
{
  "_id": "<ObjectId>",
  "leaderboard_gap": 4,
  "leaderboard_cooldown_days": 7,
  "min_progress_points": 50,
  "max_accounts_per_gamer": 10,
  "inactivity_escalation_days": 3,
  "inactivity_day_buffer_hours": 6
}
```

| Field | Default | Purpose |
|---|---|---|
| `leaderboard_gap` | 4 | Rows shown above/below the requesting gamer |
| `leaderboard_cooldown_days` | 7 | Reserved, not currently read at runtime |
| `min_progress_points` | 50 | Minimum tower point delta per sync to count as good progress |
| `max_accounts_per_gamer` | 10 | Maximum simultaneous accounts per gamer |
| `inactivity_escalation_days` | 3 | Calendar days of no progress before support escalation |
| `inactivity_day_buffer_hours` | 6 | **Dead field.** Kept for backwards compat; not read at runtime. Inactivity uses calendar days. |

---

## `messages`

Per-user message ID history for chat cleanup. Written on every interaction.

```json
{
  "_id": "<ObjectId>",
  "id": 123456789,
  "default": [111, 222, 333],
  "game": [444, 555]
}
```

| Field | Notes |
|---|---|
| `id` | Telegram user ID |
| `default` | Default message folder — most screens |
| `game` | Secondary folder — for game-specific message stacks |

**Index:** `id` unique.

---

## MongoDb method index

All methods in `mongodb.py`. Arguments shown as types; all are async.

### Roles
| Method | Query |
|---|---|
| `is_superadmin(user_id)` | `{id, superadmin: True}` |
| `is_admin(user_id)` | `{id, superadmin: False}` |
| `is_operator(user_id)` | delegates to `get_operator({id})` |
| `is_support(user_id)` | `support.find_one({id})` |

### Gamers
| Method | Notes |
|---|---|
| `get_gamer(user_id: int)` | By Telegram ID |
| `get_gamer_by_id(oid: ObjectId)` | By MongoDB `_id` |
| `add_gamer(id, username, referral, address)` | |
| `update_gamer(search, gamer)` | Also resolves `referral_name → referral` |
| `update_gamer_address(user_id, address)` | |

### Accounts
| Method | Notes |
|---|---|
| `get_account(profile: str)` | By profile string |
| `get_account_by_object_id(oid: ObjectId)` | Used in callback handlers |
| `get_accounts(search, sort)` | |
| `get_gamer_accounts(gamer_oid: ObjectId)` | All accounts for one gamer |
| `get_active_assigned_accounts()` | `status=active, gamer_id != null` |
| `put_account(profile, data, upsert)` | Generic upsert |
| `push_progress_entry(profile, entry)` | Appends to `progress_history` |
| `set_account_status(profile, status, extra_fields)` | Generic status update |
| `release_account(profile, status, released_at)` | Closes ownership, clears gamer_id, `$unset` pending_proof + release_request |
| `request_account_release(profile, gamer_oid)` | Sets `pending_release` |
| `store_proof(profile, gamer_tg_id, message_id)` | Stores `pending_proof` |

### Season 3 / Season 4
| Method | Notes |
|---|---|
| `get_gamer_season_points(gamer_oid)` | Single gamer's score via aggregation |
| `get_all_gamers_season_points()` | Full leaderboard — one DB round-trip |
| `check_assignment_eligibility(gamer_oid, config)` | Returns `(bool, reason_str)`. Conditions: slot count + progress check with gamer_id ownership guard. |
| `pickup_account(gamer_oid)` | Atomic find-and-assign. Priority 1: previously owned. Priority 2: inactive-previous-owner or no owner. Returns assigned doc or `None`. |
| `mark_gamer_season_active(gamer_oid)` | Sets `season_picked_up=True`. Idempotent. |

### Support
| Method | Notes |
|---|---|
| `get_support_users(search)` | All or filtered |
| `count_support_users(search)` | |
| `is_support(user_id)` | |
| `add_support(contact)` | From Telegram contact object |
| `remove_support(search)` | |

### Config
| Method | Notes |
|---|---|
| `get_config()` | Returns single config document |
| `update_config(field, value)` | Upserts one field |

### Messages
| Method | Notes |
|---|---|
| `push_message_history(user_id, folder, msg_id)` | |
| `get_message_history(user_id, folder, last)` | `last > 0` returns all except last N |
| `clean_message_history(user_id, folder, last)` | Clears history (keeps last N if specified) |
