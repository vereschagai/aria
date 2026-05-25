# CLAUDE.md

This file is the authoritative entry point for Claude Code when working on this codebase.
Read it fully before making any changes. When design decisions are updated in Cowork, this
file is updated first — treat it as the source of truth over any older comments in the code.

---

## Workflow

| Role | Tool |
|---|---|
| System design, architecture decisions | Cowork chat |
| Implementation | Claude Code (this tool) |
| Code review | Cowork chat |

Do not push to git or deploy from Claude Code. Commit, push, and deploy are done manually by the user after Cowork review.

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

Google Sheets spreadsheet ID and superadmin Telegram ID are hardcoded in `main.py`.
Google Sheets auth uses `client_secret.json` (service account — gitignored, must be present at runtime).

---

## Deployment

Managed by PM2 via `deployment.config.js` (gitignored — contains secrets).
Copy `deployment.config.js.example` as a template.

```bash
npm run deploy-prod       # git pull + pip install + pm2 reload on production
npm run deploy-qa         # deploy to QA
npm run rollback-prod     # git reset --hard HEAD~1 + pip install + pm2 reload on production
npm run rollback-qa       # same on QA
npm run logs-prod         # tail production logs
npm run error-logs-prod   # tail production error logs
npm run logs-qa / error-logs-qa
```

| Env | Host | DB name | PM2 process |
|---|---|---|---|
| production | `176.29.100.183:2223` | `aria` | `aria-telegram-bot-production` |
| QA | `95.111.241.149:22` | `aria_qa` | `aria-telegram-bot-qa` |

---

## Architecture

Async Python Telegram bot built on **aiogram 2.x** with FSM conversation model.
All persistent state (including FSM state) lives in **MongoDB** via the async Motor driver.
`MongoStorage` from aiogram connects FSM state directly to MongoDB.

### Role hierarchy

Resolved on every `/start` and every back-navigation, in this priority order:

```
superadmin → admin → operator → support → gamer
```

Resolution: sequential `await db.is_*()` calls in `main.py::start()` and `OperatorController.main()`.
If none match, the user is an uninvited newcomer (invite-only via referral link).

**Superadmin** is seeded from the `superadmins` list hardcoded in `main.py` and stored
in the `admin` collection with `superadmin: True`.

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
│   └── superadmin_feed                 (awaiting message to broadcast)
│
├── admin_start
│   ├── admin_add_operator              (awaiting phone contact)
│   ├── admin_add_support               (awaiting phone contact)
│   ├── admin_remove_operator           (awaiting inline button)
│   ├── admin_remove_operator_confirm
│   ├── support_remove                  (awaiting inline button)
│   └── support_remove_confirm
│
├── operator_start
│
├── support_start
│
└── start                               (gamer home)
    ├── referral                        (showing referral link)
    ├── account                         (showing account details)
    │   ├── address                     (awaiting BSC wallet — first time)
    │   └── change_address              (awaiting BSC wallet — update)
    ├── leaderboard
    └── gamer_release_account           (awaiting inline account selection)
```

---

## Module reference

### Core application

| File | Purpose |
|---|---|
| `main.py` | Entry point. Declares globals (`bot`, `dp`, `db`, `api`, `synchonizer`, `progress_monitor`, `operator_controller`). Registers all `@dp.message_handler` / `@dp.callback_query_handler` decorators for superadmin, admin, and gamer flows. Global `@dp.errors_handler()` catches and logs all unhandled exceptions. Calls `operator_controller.init_handlers()` at the bottom. |
| `state.py` | `TelegramState(StatesGroup)` — exhaustive list of all FSM states. Add every new state here. |
| `config.py` | In-memory config defaults dict synced to MongoDB `config` collection on startup via `init()`. Add new tunable parameters here. |

### Data layer

| File | Purpose |
|---|---|
| `mongodb.py` | `MongoDb` class — all async database operations. One method per logical action. `ensure_indexes()` called at startup. See [docs/data-model.md](docs/data-model.md) for full schema. |

### Controllers

| File | Purpose |
|---|---|
| `operator_controller.py` | `OperatorController(dp, bot, db)` — handles leaderboard (all roles) and role-routing via `main()`. Season 3 leaderboard uses `get_all_gamers_season_points()` aggregation. Registered via `init_handlers()`. |

### External integrations

| File | Purpose |
|---|---|
| `google_api.py` | `GoogleSheets` — reads the gameplay spreadsheet via service account. Uses a synchronous HTTP client with its own event loop. Do not `await` it directly. |
| `sheet_synchonizer.py` | `GoogleSheetSynchonizer` — parses sheet rows, computes progress deltas, upserts to MongoDB. **Never touches `gamer_id` or ownership** (Option C — assignment is DB-only). Triggers `ProgressMonitor.check_all()` after every sync. |

### Background jobs

| File | Purpose |
|---|---|
| `progress_monitor.py` | `ProgressMonitor(bot, db)` — inactivity detection and support escalation. Called after every sheet sync. Measures inactivity in **calendar days** (UTC). 1 day → warn gamer; N days (config `inactivity_escalation_days`, default 3) → escalate to support. |

### UI layer

| File | Purpose |
|---|---|
| `texts.py` | All bot message strings. Template variables use `.format()`. MarkdownV2 strings have special chars pre-escaped with backslashes. |
| `buttons.py` | Button label constants. Match these exactly in `Text(equals=...)` filters. |
| `markups.py` | Pre-built `ReplyKeyboardMarkup` objects. One markup per screen. |

### Utilities

| File | Purpose |
|---|---|
| `utils.py` | `safe_wrap()` (tenacity retry), `add_message_history()`, `clean_messages()`, `escape()` (MarkdownV2 escaping). |

### Standalone scripts

| File | Purpose |
|---|---|
| `mongo_scripts.py` | Season 3 reward calculation. Uses `get_all_gamers_season_points()` aggregation to distribute a USDT pool proportionally by Season 3 score. Run locally against production DB; not part of the bot process. |
| `migration_season3.py` | One-time migration for Season 3. Snapshots `season3_start_points`, seeds `gamer_id`, `ownership_history`, `progress_history`, `status`, etc. Already applied; do not re-run. |
| `migration_season4.py` | One-time migration for Season 4. Converts each account: seeds `progress_history[0]` from `season3_start_points`, closes open `ownership_history` entries, sets `status="released"`, removes `season3_start_points` and `available_for_pickup`. Run once on production before Season 4 bot deploy. Idempotent (skips accounts already migrated). |

---

## Data model

Full schema in [docs/data-model.md](docs/data-model.md). Summary below.

### `admin`
Superadmins and admins. `superadmin: true` distinguishes them.
Index: `(id, superadmin)` compound.

### `operators`
Index: `id` unique.

### `support`
Managed identically to operators (contact-based add/remove via admin). Index: `id` unique.

### `gamers`
Indexes: `id` unique, `username` sparse, `referral`, `season_picked_up` sparse.

`season_picked_up` (bool, absent = falsy) — set to `true` on first account pickup this season. Used by `pickup_account()` to identify inactive-previous-owner accounts eligible for priority-2 reassignment.

### `accounts`
One document per game account. Upserted from Google Sheets by `GoogleSheetSynchonizer`.
**`gamer_id` and ownership fields are NEVER written by the synchonizer** (Option C).

**Account statuses:**

| Status | Meaning |
|---|---|
| `active` | Normally assigned, gamer is playing |
| `escalated` | Forwarded to support — awaiting decision |
| `pending_release` | Gamer requested release — awaiting support decision |
| `released` | Freed; open for reassignment via `pickup_account()` |
| `inactive` | Closed by support; no future assignment |

### `config`

| Field | Default | Purpose |
|---|---|---|
| `leaderboard_gap` | 4 | Rows shown above/below the requesting gamer |
| `leaderboard_cooldown_days` | 7 | (reserved, unused) |
| `min_progress_points` | 50 | Tower point delta per sync to count as good progress |
| `max_accounts_per_gamer` | 10 | Max simultaneous accounts per gamer |
| `inactivity_escalation_days` | 3 | Calendar days of no progress before escalation |
| `inactivity_day_buffer_hours` | 6 | **Dead field** — kept for backwards compat; not read at runtime |

---

## Google Sheets integration

- **Sheet ID**: `18NtTSuIWVU9sGdnJ_NGlnsowPD1oBtUyZmCULvmAcZ4`
- **Tab**: `Accounts`, range `A2:AQ`
- **Sync trigger**: manual — superadmin taps "Акки на базу"

### Column layout (0-indexed)

| Index | Content | Synchonizer action |
|---|---|---|
| 0 | Profile | Identity key |
| 1 | Login | Updated |
| 2 | Password | Updated |
| 3 | Proxy (`host:port:login:pass` or `#N/A`) | Updated; `#N/A` → skip row |
| 4 | Old Gamer (Season 1) | **Ignored** |
| 5 | Active (`#N/A` = inactive in S3) | `#N/A` → skip row |
| 6 | Gamer (S3 sheet column) | **Ignored** (DB-only assignment) |
| 7 | TP Start (`points;rank;floor`) | Seed `progress_history[0]` entry for new accounts only (delta = start_points, gamer_id = null) |
| 8+ | Daily sync columns (`points;rank;floor`) | `account[-1]` = most recent; used for delta |

Tower column format: `points;rank;floor` (three semicolon-separated integers). `NaN` and empty values are treated as `0`.

---

## Season 3 system

See [docs/season3-system-design.md](docs/season3-system-design.md) for original design decisions.

### Scoring

A gamer's Season 3 score = **Σ positive `progress_history.delta`** where `entry.gamer_id == gamer._id`, across ALL accounts (current and past). Negative deltas (game resets) are ignored. A gamer keeps points earned on an account even after releasing it.

Single aggregation in `mongodb.get_all_gamers_season_points()` covers the entire leaderboard in one DB round-trip.

### Inactivity monitoring (`progress_monitor.py`)

Runs after every sync. For each `status=active` account with a `gamer_id`:

```
baseline = last_progress_at  OR  ownership_history[-1].assigned_at
days_inactive = (today_utc - baseline.date()).days
```

- `days_inactive >= 1`: warn gamer once per calendar day (deduplicated via `last_notified_day` ordinal)
- `days_inactive >= inactivity_escalation_days` and `status != "escalated"`: escalate to all support users

---

## Season 4 system

See [docs/season4-system-design.md](docs/season4-system-design.md) for full ADR.

### Account pickup — instant auto-assign

Replaces the Season 3 "request → operator notify → manual sync" flow.

`start` → tap "🎮 Взять аккаунт" → `db.check_assignment_eligibility()` → `db.pickup_account()` → confirms with credentials.

No operator notification. No `request_account` FSM state. The handler stays in `start` throughout.

### Assignment eligibility check

`mongodb.check_assignment_eligibility(gamer_object_id, config)` → `(bool, reason_str)`.

Both must hold:
1. Occupied slots (`active` + `escalated` + `pending_release`) < `max_accounts_per_gamer`
2. All strictly `active` accounts: `progress_history[-1].gamer_id == this_gamer` **and** `progress_history[-1].delta >= min_progress_points` (escalated and pending_release accounts are exempt from this check)

### Account pickup priority (`mongodb.pickup_account`)

Atomic `findOneAndUpdate` with `status == "released"` guard. Priority order:

1. **Priority 1** — accounts previously owned by this gamer (`ownership_history.gamer_id` contains their `_id`), sorted descending by `tower.points`
2. **Priority 2** — remaining released accounts whose last owner has `season_picked_up != true` (i.e., inactive this season) or has no previous owner, sorted descending by `tower.points`

Sets: `gamer_id`, `status = "active"`, pushes new `ownership_history` entry.
Then: `db.mark_gamer_season_active(gamer._id)` sets `season_picked_up = true` (idempotent).

---

## Key patterns

### All Telegram API calls — always use safe_wrap

```python
sent = await utils.safe_wrap(lambda: message.answer("text", reply_markup=markups.start))
```

`safe_wrap` applies tenacity exponential backoff (1–60 s) on transient Telegram API errors.

### Message cleanup

Every screen transition must track and clean messages:

```python
await utils.add_message_history(db, message)          # track incoming
await utils.clean_messages(bot, db, user_id)           # delete previous batch
sent = await utils.safe_wrap(lambda: bot.send_message(...))
await utils.add_message_history(db, sent)              # track outgoing
```

### MarkdownV2 escaping

All dynamic content in `parse_mode="MarkdownV2"` messages must go through `utils.escape()`:

```python
texts.some_template.format(username=utils.escape(gamer["username"]))
```

Static strings in `texts.py` already have special chars pre-escaped.

### Callback data — always use ObjectId hex

Telegram limits `callback_data` to 64 bytes. Profile names can exceed this limit. Always use
the account's MongoDB `_id` as a 24-char hex string:

```python
# Building the keyboard:
callback_data=f"my_action:{str(account['_id'])}"

# In the callback handler:
action, oid_str = callback_query.data.split(":", 1)
account = await db.get_account_by_object_id(ObjectId(oid_str))
```

### Gamer None guard

`db.get_gamer(user_id)` can return `None`. Always guard before accessing fields:

```python
gamer = await db.get_gamer(message.from_user.id)
if not gamer:
    return
```

### Adding a new handler

1. Add FSM states to `state.py`.
2. Add button labels to `buttons.py`, markups to `markups.py`, strings to `texts.py`.
3. Register in `main.py` with `@dp.message_handler(Text(equals=buttons.X), state=TelegramState.Y)`, or inside `OperatorController.init_handlers()`.
4. If accessible from multiple roles, register once per relevant state.
5. For account lookups from callbacks, use ObjectId hex (see pattern above).
6. **Update CLAUDE.md and the relevant doc in `docs/` before implementing.**

---

## Known gaps

| # | Gap | File | Notes |
|---|---|---|---|
| 1 | `inactivity_day_buffer_hours` config field is dead | `config.py`, `mongodb.py` | Inactivity uses calendar days; field kept for backwards compat |
| 2 | Support home has no "active escalations" list | `markups.py`, `main.py` | Design doc mentioned this; not yet implemented |
| 3 | Sheet sync is manual | `sheet_synchonizer.py` | Automation via Octo+Puppeteer is a separate future project |
| 4 | No automated tests | — | Test strategy TBD |
