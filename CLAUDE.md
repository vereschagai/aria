# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the bot

```bash
python3 main.py
```

Environment variables (defaults to local MongoDB if unset):
- `BOT_TOKEN` — Telegram bot token
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USERNAME`, `DB_PASSWORD` — MongoDB connection

## Deployment

Managed by PM2 via `deployment.config.js`. npm scripts wrap remote commands:

```bash
npm run deploy-prod    # deploy to production
npm run logs-prod      # tail production logs
npm run deploy-qa      # deploy to QA
npm run logs-qa        # tail QA logs
```

## Architecture

This is an async Python Telegram bot built on **aiogram 2.x** with a finite-state-machine (FSM) conversation model. All persistent state (including FSM state) is stored in MongoDB via the async Motor driver.

### Role hierarchy

Users fall into one of five roles, checked in order on every `/start`:
`superadmin` → `admin` → `operator` / `payer` / `validator` → `gamer`

Each role has its own set of `TelegramState` states (defined in `state.py`) and corresponding handlers in `main.py` or `operator_controller.py`.

### Module responsibilities

| File | Purpose |
|---|---|
| `main.py` | Bot entry point; all `@dp.message_handler` / `@dp.callback_query_handler` registrations for superadmin, admin, and gamer flows |
| `state.py` | `TelegramState(StatesGroup)` — exhaustive list of all FSM states |
| `mongodb.py` | `MongoDb` class — all async database operations, one method per logical action |
| `operator_controller.py` | `OperatorController` class — operator-specific handlers registered via `init_handlers()` |
| `texts.py` | All bot message strings (Russian) |
| `buttons.py` | Button label constants |
| `markups.py` | Pre-built `ReplyKeyboardMarkup` / `InlineKeyboardMarkup` objects |
| `google_api.py` | `GoogleSheets` — reads/writes the gameplay spreadsheet via service account (`client_secret.json`) |
| `sheet_synchonizer.py` | `GoogleSheetSynchonizer` — imports accounts from Google Sheets into MongoDB |
| `utils.py` | `safe_wrap` (tenacity retry for Telegram API calls), message-history cleanup helpers, MarkdownV2 `escape()` |
| `config.py` | In-memory config defaults synced to MongoDB `config` collection on startup |

### Key patterns

**Adding a new handler**: Register it with `@dp.message_handler(Text(equals=buttons.X), state=TelegramState.Y)` in `main.py`, or via `dp.register_message_handler(...)` inside `OperatorController.init_handlers()`. Always call `operator_controller.init_handlers()` is already done at the bottom of `main.py` after all inline handlers.

**All Telegram API calls** must be wrapped with `await utils.safe_wrap(lambda: ...)` to get automatic exponential-backoff retries on transient errors.

**Message cleanup**: Bot deletes previous messages on screen transitions. Call `add_message_history(db, message)` for every sent message, then `clean_messages(bot, db, user_id)` to delete the previous batch before sending new ones.

**MarkdownV2**: All user-facing messages that use `parse_mode="MarkdownV2"` must escape dynamic content through `utils.escape()`.

**Config**: Runtime-tunable parameters live in the MongoDB `config` collection. Access via `await db.get_config()`. Defaults are declared in `config.py` and written on first startup.
