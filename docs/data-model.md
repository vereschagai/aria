# Data Model

All data is stored in MongoDB. The database name is configured via `DB_NAME` env var (`aria` for production, `aria_qa` for QA). FSM state is also stored in MongoDB via aiogram's `MongoStorage` (in a separate `fsm` collection managed automatically).

---

## Collections

### `admin`

Stores superadmins and admins. Distinguished by the `superadmin` boolean field.

```js
{
  id: Number,         // Telegram user ID (required)
  phone: String,      // from Telegram contact share (required at creation)
  username: String,   // populated on first /start after being added (optional)
  superadmin: Boolean // true = superadmin, false = admin
}
```

Index: `(id, superadmin)` compound ascending.

Superadmin is seeded automatically from the hardcoded list in `main.py` if not already present.

---

### `operators`

```js
{
  id: Number,    // Telegram user ID (required)
  phone: String  // from Telegram contact share (required at creation)
}
```

Index: `id` unique ascending.

---

### `gamers`

One document per guild member (gamer role).

```js
{
  id: Number,            // Telegram user ID (set when user first /start's)
  username: String,      // Telegram @username (without @)
  referral: Number,      // Telegram ID of the referrer (null if no referrer)
  referral_name: String, // TEMPORARY: @username of referrer when ID unknown at registration time
                         // cleared and replaced by referral (ID) on first successful login
  address: String        // BSC/EVM wallet address (null until set)
}
```

Indexes: `id` unique, `username` sparse, `referral` ascending.

**Referral resolution**: When a user registers without a Telegram ID for their referrer (rare edge case), `referral_name` stores the username. When any user with that username logs in, `update_gamer` resolves `referral_name` → `referral` automatically via `$set` + `$unset`.

---

### `accounts`

One document per game account. Managed entirely by `GoogleSheetSynchonizer` (read from Google Sheets, upserted here). Gamers see their own accounts via the "👤 Мой аккаунт" screen.

```js
{
  profile: String,     // unique game profile name (sheet col A) — upsert key
  login: String,       // game account email/login (sheet col B)
  password: String,    // game account password (sheet col C)
  proxy: {
    host: String,
    port: Number,
    login: String,
    password: String
  },                   // parsed from sheet col D: "host:port:login:pass"
                       // empty object {} if proxy not set
  gamer: String,       // @username (without @) of the gamer this account belongs to
                       // links to gamers.username (sheet col E)
                       // null if unassigned
  points: {
    points: Number,    // game points
    rank: Number       // game rank
  },
  tower: {
    points: Number,    // tower game points
    rank: Number,      // tower rank
    floor: Number      // tower current floor
  }
}
```

Sheet last-column format: `"points;rank;tower_points;tower_rank;tower_floor"` — all 5 values separated by semicolons. Missing or non-numeric values default to 0.

Indexes: `profile` unique, `gamer` ascending, `(points.points, DESCENDING)`.

---

### `config`

Single document. Created on first startup with defaults from `config.py`. Editable at runtime by superadmin via ⚙️ Конфигурация menu.

```js
{
  _id: ObjectId,
  leaderboard_gap: Number,          // rows to show above and below gamer's rank (default: 4)
  leaderboard_cooldown_days: Number // currently unused in code (default: 7)
}
```

Access via `await db.get_config()`. The config document is always a single record (no filter used on find).

---

### `messages`

Per-user message history for UI cleanup. Updated on every screen transition.

```js
{
  id: Number,       // Telegram user ID
  default: [Number], // message IDs in the "default" folder (most screens)
  game: [Number]     // message IDs in the "game" folder (game session screens)
}
```

Index: `id` unique.

**Cleanup mechanics**: `clean_messages(bot, db, user_id, folder, last)` deletes all message IDs in the folder (or all except the last `n` if `last > 0`), then clears the stored history.

---

## MongoDb method reference

| Method | Collection | Description |
|---|---|---|
| `get_config()` | config | Get single config document |
| `update_config(field, value)` | config | Upsert a config field |
| `is_superadmin(user_id)` | admin | Check if user is superadmin |
| `add_superadmin(admin)` | admin | Insert superadmin |
| `get_admins()` | admin | List all non-superadmin admins |
| `count_admins(search)` | admin | Count admins matching search |
| `is_admin(user_id)` | admin | Check if user is a regular admin |
| `get_admin(search)` | admin | Get one admin by search dict |
| `add_admin(contact)` | admin | Add admin from Telegram contact |
| `remove_admin(search)` | admin | Delete one admin |
| `get_operators(search)` | operators | List operators |
| `count_operators(search)` | operators | Count operators |
| `is_operator(user_id)` | operators | Check if user is operator |
| `get_operator(search)` | operators | Get one operator |
| `add_operator(contact)` | operators | Add operator from Telegram contact |
| `remove_operator(search)` | operators | Delete one operator |
| `is_gamer(search)` | gamers | Check if gamer exists |
| `count_gamers(search)` | gamers | Count gamers matching search |
| `get_gamers(search, sort)` | gamers | List gamers |
| `get_gamer(user_id)` | gamers | Get one gamer by Telegram ID |
| `add_gamer(id, username, referral, address)` | gamers | Insert new gamer |
| `update_gamer(search, gamer)` | gamers | Update gamer, auto-resolves referral_name |
| `update_gamer_address(user_id, address)` | gamers | Set BSC wallet address |
| `get_accounts(search, sort)` | accounts | List accounts |
| `put_account(profile, data, upsert)` | accounts | Upsert account by profile name |
| `push_message_history(user_id, folder, message_id)` | messages | Append message ID to folder |
| `get_message_history(user_id, folder, last)` | messages | Get stored message IDs |
| `clean_message_history(user_id, folder, last)` | messages | Clear stored message IDs |
| `ensure_indexes()` | all | Create all indexes (called on startup) |
