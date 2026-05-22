# CLAUDE.md

This file provides guidance to Claude when working with the Aria Telegram bot codebase.

---

## Quick start

```bash
python3 main.py
```

Environment variables (all optional — fall back to local defaults when unset):

| Variable | Default | Purpose |
|---|---|---|
| `BOT_TOKEN` | hardcoded test token in `main.py` | Telegram bot token |
| `DB_HOST` | `localhost` | MongoDB host |
| `DB_PORT` | `27017` | MongoDB port |
| `DB_NAME` | `aria` | MongoDB database name |
| `DB_USERNAME` | _(none)_ | MongoDB auth username |
| `DB_PASSWORD` | _(none)_ | MongoDB auth password |

The Google Sheets spreadsheet ID (`ARIA_GAMEPLAY_SHEET_ID`) and the superadmin Telegram user ID (`208809955`) are hardcoded in `main.py`. Google Sheets auth uses `client_secret.json` (service account, gitignored).

---

## Deployment

Managed by PM2 via `deployment.config.js` (gitignored — contains secrets). npm scripts wrap remote PM2 commands:

```bash
npm run deploy-prod       # git pull + pip install + pm2 reload on production
npm run logs-prod         # tail production logs
npm run error-logs-prod   # tail production error logs only
npm run deploy-qa         # deploy to QA
npm run logs-qa           # tail QA logs
npm run error-logs-qa     # tail QA error logs
```

**Environments:**

| Env | Host | DB name | PM2 process |
|---|---|---|---|
| production | `176.29.100.183:2223` | `aria` | `aria-telegram-bot-production` |
| QA | `95.111.241.149:22` | `aria_qa` | `aria-telegram-bot-qa` |

Post-deploy hook: `pip install -r requirements.txt && pm2 reload deployment.config.js --env <env> --force`

---

## Architecture

Async Python Telegram bot built on **aiogram 2.x** with a finite-state-machine (FSM) conversation model. All persistent state (including FSM state) is stored in **MongoDB** via the async Motor driver. `MongoStorage` from aiogram connects FSM state storage directly to MongoDB.

### Role hierarchy

Every incoming `/start` message resolves the user's role in this priority order:

```
superadmin → admin → operator → gamer
```

Resolution is done by sequential `await db.is_*()` calls in `main.py::start()` and `OperatorController.main()`. If none match, the user is treated as a potential newcomer gamer (invite-only via referral link).

**Superadmin** is seeded from the `superadmins` list hardcoded in `main.py` and stored in the `admin` collection with `superadmin: True`.

### FSM state map

All states live in `state.py::TelegramState(StatesGroup)`.

```
TelegramState
├── superadmin_start
│   ├── superadmin_add_admin            (awaiting phone contact)
│   ├── superadmin_remove_admin         (awaiting inline button selection)
│   ├── superadmin_remove_admin_confirm
│   ├── superadmin_configuration        (awaiting inline button = field name)
│   ├── superadmin_edit_configuration   (awaiting new value text)
│   └── superadmin_feed                 (awaiting any message to broadcast)
│
├── admin_start
│   ├── admin_add_operator              (awaiting phone contact)
│   ├── admin_remove_operator           (awaiting inline button selection)
│   └── admin_remove_operator_confirm
│
├── operator_start
│
└── start                               (gamer home)
    ├── referral                        (showing referral link)
    ├── account                         (showing account details)
    │   ├── address                     (awaiting new BSC wallet address — first time)
    │   └── change_address              (awaiting new BSC wallet address — update)
    └── leaderboard
```

---

## Module reference

### Core application

| File | Purpose |
|---|---|
| `main.py` | Bot entry point. Declares globals (`bot`, `dp`, `db`, `api`, `synchonizer`, `operator_controller`). Registers all `@dp.message_handler` / `@dp.callback_query_handler` decorators for superadmin, admin, and gamer flows. Calls `operator_controller.init_handlers()` at the bottom. |
| `state.py` | `TelegramState(StatesGroup)` — exhaustive list of all FSM states. Add every new state here. |
| `config.py` | In-memory config defaults dict synced to MongoDB `config` collection on startup. Add new tuneable parameters here. |

### Data layer

| File | Purpose |
|---|---|
| `mongodb.py` | `MongoDb` class — all async database operations. One method per logical action. Also contains `ensure_indexes()` called at startup. |

### Controllers

| File | Purpose |
|---|---|
| `operator_controller.py` | `OperatorController` class — handles leaderboard (accessible to all roles) and role-routing via `main()`. Registered via `init_handlers()`. |

### External integrations

| File | Purpose |
|---|---|
| `google_api.py` | `GoogleSheets` — reads the gameplay spreadsheet via service account. Uses a dedicated `asyncio` event loop internally (synchronous google-api-python-client). |
| `sheet_synchonizer.py` | `GoogleSheetSynchonizer` — parses sheet rows into account documents and upserts them into MongoDB via `db.put_account()`. Triggered manually by superadmin via "Акки на базу" button. |

### UI layer

| File | Purpose |
|---|---|
| `texts.py` | All bot message strings in Russian. Template variables use `.format()`. MarkdownV2 strings have literal backslash-escaped special chars baked in. |
| `buttons.py` | Button label constants. Match these exactly in `Text(equals=...)` filters. |
| `markups.py` | Pre-built `ReplyKeyboardMarkup` objects. One markup per screen. |

### Utilities

| File | Purpose |
|---|---|
| `utils.py` | `safe_wrap()` (tenacity retry), `add_message_history()`, `clean_messages()`, `escape()` (MarkdownV2 escaping). |

### Standalone scripts

| File | Purpose |
|---|---|
| `mongo_scripts.py` | One-off reward calculation script. Queries accounts, aggregates tower points per gamer, distributes a given USDT amount proportionally, prints `address,amount` CSV. Run locally; not part of the bot process. |

### Gitignored modules (exist as .pyc only)

These existed in earlier versions but are gitignored or removed. Do not reference unless restored:
`cctools`, `challenge_controller`, `challenge_operator`, `dive`, `fingerprint`, `flask_server`, `octo_api`, `proxifier`, `task_controller`, `webshare_api`, `websocket_server`

---

## Data model (MongoDB collections)

### `admin`
Stores both superadmins and admins. The `superadmin` field distinguishes them.

```json
{
  "id": 208809955,
  "username": "ivanvereschaga",
  "phone": "+7...",
  "superadmin": true
}
```

Indexes: `(id, superadmin)` compound.

### `operators`
```json
{
  "id": 123456789,
  "phone": "+7..."
}
```

Index: `id` unique.

### `gamers`
```json
{
  "id": 123456789,
  "username": "telegramhandle",
  "referral": 987654321,       // Telegram ID of referrer (or null)
  "referral_name": "handle",  // temporary: resolved to "referral" ID on first login
  "address": "0x..."          // BSC wallet (nullable until set)
}
```

Indexes: `id` unique, `username` sparse, `referral`.

### `accounts`
One document per game account. Upserted from Google Sheets by `GoogleSheetSynchonizer`.

```json
{
  "profile": "ProfileName",
  "login": "email@example.com",
  "password": "secret",
  "proxy": {
    "host": "1.2.3.4",
    "port": 8080,
    "login": "proxyuser",
    "password": "proxypass"
  },
  "gamer": "telegramhandle",  // links to gamers.username (no @ prefix)
  "points": { "points": 1500, "rank": 42 },
  "tower": { "points": 300, "rank": 10, "floor": 5 }
}
```

Sheet column layout (0-indexed): `[0]` profile · `[1]` login · `[2]` password · `[3]` proxy string (`host:port:login:pass`) · `[4]` gamer handle · `[last]` points string (`points;rank;tower_points;tower_rank;tower_floor`).

Indexes: `profile` unique, `gamer`, `(points.points, DESCENDING)`.

### `config`
Single document, runtime-editable by superadmin.

```json
{
  "leaderboard_gap": 4,
  "leaderboard_cooldown_days": 7
}
```

Access via `await db.get_config()`. Update via superadmin → ⚙️ Конфигурация in-bot.

### `messages`
Per-user message history for cleanup.

```json
{
  "id": 123456789,
  "default": [111, 222, 333],
  "game": [444, 555]
}
```

Index: `id` unique.

---

## Key patterns

### Adding a new handler

1. Add FSM states to `state.py`.
2. Add button labels to `buttons.py`, markups to `markups.py`, strings to `texts.py`.
3. Register in `main.py` with `@dp.message_handler(Text(equals=buttons.X), state=TelegramState.Y)`, or inside `OperatorController.init_handlers()` via `dp.register_message_handler(...)`.
4. If the handler should be accessible from multiple roles, register it once per relevant state (see `__leaderboard` in `operator_controller.py`).

### All Telegram API calls — always use safe_wrap

```python
sent = await utils.safe_wrap(lambda: message.answer("text", reply_markup=markups.start))
```

`safe_wrap` applies tenacity exponential backoff (1–60 s) on transient Telegram API errors.

### Message cleanup pattern

Every screen transition must track and clean messages:

```python
await utils.add_message_history(db, message)         # track incoming
await utils.clean_messages(bot, db, user_id)          # delete previous batch
sent = await utils.safe_wrap(lambda: bot.send_message(...))
await utils.add_message_history(db, sent)             # track outgoing
```

The `folder` parameter (default `"default"`) lets you manage separate message stacks (e.g., `"game"`).

### MarkdownV2 escaping

All dynamic content in `parse_mode="MarkdownV2"` messages must go through `utils.escape()`:

```python
texts.some_template.format(username=utils.escape(gamer["username"]))
```

Static strings in `texts.py` already have special chars pre-escaped.

### Config access

```python
db_config = await db.get_config()
gap = db_config["leaderboard_gap"]
```

### Leaderboard algorithm

Aggregates `accounts.points.points` per `gamer` username, sorts descending, then shows a window of `leaderboard_gap` rows above and below the requesting gamer's rank. Non-gamer users (admin/operator/superadmin) see the full list.

### Referral system

Invite-only access. New gamers must arrive via `https://t.me/<botname>?start=<referrer_telegram_id>`. The referrer ID is validated (must be an existing gamer/admin/superadmin/operator; cannot be self). If the newcomer has no Telegram username yet, the referral ID is stored in FSM state and resolved after they set a username.

### Wallet address validation

BSC addresses are validated with the `cryptoaddress` library:

```python
from cryptoaddress import EthereumAddress
EthereumAddress(message.text)  # raises ValueError on invalid input
```

---

## Google Sheets integration

- **Sheet ID**: `18NtTSuIWVU9sGdnJ_NGlnsowPD1oBtUyZmCULvmAcZ4`
- **Tab**: `Accounts`, range `A2:AQ`
- **Auth**: service account via `client_secret.json` (gitignored; must be present at runtime)
- **Sync trigger**: manual — superadmin taps "Акки на базу" → `synchonizer.grab_accounts()`
- `GoogleSheets` uses a synchronous HTTP client internally; it creates its own event loop via `asyncio.new_event_loop()` and must not be awaited directly.

---

## Reward calculation (mongo_scripts.py)

Run manually (not part of bot):

```bash
python3 mongo_scripts.py
```

Calculates proportional USDT distribution based on `tower.points` per gamer across all their accounts. Output is `address,amount` CSV to stdout. Edit the `calculate_rewards(amount)` call at the bottom to set the total pool size.
