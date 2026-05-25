# CONTEXT

## Stack

**Runtime:** Python 3 (version unspecified)

**Telegram bot framework:** aiogram 2.20 — FSM, handlers, dispatcher. EOL; migration to v3 is a breaking rewrite, deferred.

**Database:** MongoDB via motor 3.0.0 (async driver). Single `MongoDb` class wraps all queries. Collections: `admins`, `operators`, `support`, `gamers`, `accounts`, `messages`, `config`.

**Google Sheets:** google-api-python-client 2.2.0 + google-auth 1.30.0. Service account auth via `client_secret.json` (gitignored, must exist at runtime). Used as a read-only data source for account credentials and tower points.

**Scheduler:** aiocron present in early requirements; retained in final `requirements.txt` alongside other cleanup.

**Process management:** PM2 (Node.js). All deploy/start/stop/rollback commands are npm scripts delegating to `deployment.config.js` (gitignored). Node is not used for application logic.

**Other Python packages:**
- `tenacity==7.0.0` — exponential backoff on DB and Sheets calls
- `cryptoaddress==0.2.1` — BSC wallet address validation
- `requests==2.31.0`

---

## Architecture

Single Python process (managed by PM2) running an aiogram 2.x Telegram bot for guild management of the "Aria AI" game.

**Core invariant (Option C):** Google Sheets is a data import source only. Account assignment is DB-only — the synchonizer never reads the `gamer` column from the sheet and never writes back.

**Component map:**

```
Telegram users
    ↓
main.py  (aiogram dispatcher — all handlers, FSM, role routing)
    ↓                              ↓
mongodb.py  (MongoDb class)    operator_controller.py  (leaderboard, role routing for operators)
    ↓
Motor → MongoDB

sheet_synchonizer.py  →  google_api.py  →  Google Sheets API
    ↓
progress_monitor.py  →  bot.send_message() (inactivity warnings + escalations)

migration_season3.py  ]  one-time scripts, run via SSH tunnel
migration_season4.py  ]
mongo_scripts.py       ]  reward calculation, run locally
```

**Role hierarchy:** superadmin → admin → operator → support → gamer

---

## Key Components

**`main.py`** (924 lines) — Entry point and monolith. Handles all Telegram message routing, FSM states, role resolution on `/start`, and the global error handler. Wires up `MongoDb`, `GoogleSheets`, `GoogleSheetSynchonizer`, `ProgressMonitor`, `OperatorController`.

**`mongodb.py`** (443 lines) — All DB logic. Key methods: `pickup_account()` (atomic auto-assignment with P1/P2 priority), `check_assignment_eligibility()` (slot + progress check), `release_account()` (closes ownership history, unsets sparse fields), `get_all_gamers_season_points()` / `get_gamer_season_points()` (aggregation pipelines), `ensure_indexes()` (creates all indexes on startup).

**`sheet_synchonizer.py`** (173 lines) — Reads Accounts tab from Google Sheets. Column layout: `[0]` profile, `[1]` login, `[2]` password, `[3]` proxy, `[4]` old gamer (ignored), `[5]` active, `[6]` gamer (ignored per Option C), `[7]` TP Start (`points;rank;floor`), `[8+]` daily columns (same format). Skips rows where Active or Proxy is `#N/A`. After all updates, calls `ProgressMonitor.check_all()`.

**`progress_monitor.py`** (172 lines) — Post-sync inactivity checks. Calendar-day delta from `last_progress_at`. Day 1–2: warning to gamer. Day 3+: escalate to all support users with last-5-progress summary + inline decision buttons.

**`operator_controller.py`** (110 lines) — Leaderboard and role-routing for operators/support. Fetches season points via single aggregation + batch username resolution (2 DB round-trips regardless of guild size).

**`state.py`** (31 lines) — All FSM states. `TelegramState(StatesGroup)` with states for all roles and flows including `gamer_release_account`, `support_start`, `support_remove`.

**`config.py`** — In-memory seed dict for the `config` MongoDB collection. Seeded on startup. Governs: `min_progress_points` (seed: 10, documented default: 50), `max_accounts_per_gamer` (10), `inactivity_escalation_days` (3), `leaderboard_gap` (4).

**`buttons.py`** / **`texts.py`** / **`markups.py`** — UI layer. Russian-language button labels, MarkdownV2 message strings, pre-built `ReplyKeyboardMarkup` objects. All bot-facing text is here, except one hardcoded string in `operator_controller.py` and a hardcoded support handle (`@goldalfsupp`) in `texts.py`.

**`utils.py`** — `escape()` (MarkdownV2), `add_message_history()` / `clean_messages()` (tracked-message cleanup), `safe_wrap()` (tenacity retry decorator).

**`google_api.py`** (36 lines) — Synchronous Google Sheets wrapper. Reads `Accounts!A2:AQ`. Uses a sync HTTP client inside async code — blocks the event loop during Sheets API calls. Not a correctness bug, but a latency risk during syncs.

**Migration scripts** (`migration_season3.py`, `migration_season4.py`) — One-time scripts run via SSH tunnel. Already applied to production; do not re-run. `mongo_scripts.py` is a standalone reward calculator.

---

## External Dependencies

| Dependency | Role |
|---|---|
| Telegram Bot API | User interface (via aiogram) |
| MongoDB | Primary data store — all bot state |
| Google Sheets API | Read-only source for account credentials and tower points |
| PM2 (Node.js) | Process management and deployment |
| Octo Browser + Puppeteer | **Parallel project (not in this repo)** — scrapes live tower points from game site daily, writes to Google Sheets column I onward |
| SSH tunnel | Used to run migration scripts against production MongoDB |

**Infrastructure:** Production server at `176.29.100.183`, QA at `95.111.241.149`. Credentials and SSH config in gitignored `deployment.config.js`.

---

## Security Notes (open issues)

- `client_secret.json` (Google service account key) is committed in the repo directory — gitignored but present; needs `git filter-branch` / BFG to remove from history.
- Bot token hardcoded in `main.py` line 30 as fallback when `BOT_TOKEN` env var is unset.
- Old test bot token on line 29 (commented out) also visible in source.
