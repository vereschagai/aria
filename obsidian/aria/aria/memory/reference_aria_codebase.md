---
name: reference-aria-codebase
description: Pointers to key locations in the Aria codebase — where to find/add
  things, env vars, infrastructure details
type: reference
updated: 2026-05-27
version: "5"
---

# Aria Codebase — Reference Pointers

See [[memory/project_aria|Project Overview]] for architecture and season state.
See [[memory/feedback_aria_workflow|Workflow Rules]] for coding patterns.
See [[CONTEXT]] for full component map.

---

## Where things live

| Thing | Location |
|---|---|
| All FSM states | `state.py` — add here first — [[modules/state]] |
| Bot message strings (Russian, MarkdownV2) | `texts.py` — [[modules/texts]] |
| Button label constants | `buttons.py` — [[modules/buttons]] |
| Pre-built keyboard markups | `markups.py` — [[modules/markups]] |
| Config defaults (seeded to MongoDB on startup) | `config.py` — [[modules/config]] |
| All DB operations | `mongodb.py` — `MongoDb` class — [[modules/mongodb]] |
| All Telegram handlers | `main.py` (~950 lines) — [[modules/main]] |
| Sheet sync logic | `sheet_synchonizer.py` — credentials-only + `sync_single_account()` — [[modules/sheet_synchonizer]] |
| Inactivity monitoring | `progress_monitor.py` — [[modules/progress_monitor]] |
| Google Sheets API wrapper | `google_api.py` — async via `run_in_executor` — [[modules/google_api]] |
| WebSocket task server | `websocket_server.py` — [[modules/websocket_server]] |
| Shared utilities | `utils.py` — [[modules/utils]] |
| Test suite | `tests/` — pytest, **85 tests**, `pytest tests/ -v` |
| Test dependencies | `requirements-test.txt` — `pytest`, `pytest-asyncio`, `mongomock` |
| Deployment npm scripts | `package.json` |
| Deployment config template | `deployment.config.js.example` |

## Obsidian vault structure (inside repo at `obsidian/aria/`)

| Path | Content |
|---|---|
| `aria/memory/MEMORY.md` | **← this memory system** — boot index |
| `aria/INDEX.md` | Full vault index — [[INDEX]] |
| `aria/CONTEXT.md` | Stack, architecture, component map — [[CONTEXT]] |
| `aria/DECISIONS.md` | All 12 ADRs — [[DECISIONS]] |
| `aria/PROGRESS.md` | What is implemented — [[PROGRESS]] |
| `aria/REVIEW.md` | Most up-to-date implementation status — [[REVIEW]] |
| `aria/flows/` | Per-flow docs (14 flows) |
| `aria/modules/` | Per-module docs (12 modules) |

---

## External services & env vars

| Service | Env var / Detail |
|---|---|
| Telegram Bot | `BOT_TOKEN` env var — raises `RuntimeError` if unset |
| Google Sheet | `ARIA_SHEET_ID` env var — raises `RuntimeError` if unset |
| Google Sheets tab | `Accounts`, range `A2:AQ` |
| Google auth | `client_secret.json` (gitignored — must be present at runtime) |
| Support Telegram handle | `support_handle` in `config.py` (default `@goldalfsupp`) |

---

## Infrastructure

| Env | Host | DB | PM2 process |
|---|---|---|---|
| Production | `176.29.100.183:2223` | `aria` | `aria-telegram-bot-production` |
| QA | `95.111.241.149:22` | `aria_qa` | `aria-telegram-bot-qa` |

---

## MongoDB collections

| Collection | Key indexes |
|---|---|
| `support` | `id` unique |
| `gamers` | `id` unique, `username` sparse, `referral`, `season_picked_up` sparse, `pool_release_count` |
| `accounts` | `profile` unique, `gamer_id`, `status`, `last_progress_at`, `tower.points`, `progress_history.gamer_id`, `ownership_history.gamer_id` |
| `release_blocks` | compound unique `(account_id, gamer_id)` — prevents re-pickup of released accounts |
| `messages` | `id` unique |
| `config` | — |
| `tasks` | `status`, `type`, `profile` |

**`release_blocks` schema:**
```
{
  account_id: ObjectId,   ← ref to accounts._id
  gamer_id:   ObjectId,   ← ref to gamers._id
  blocked_at: DateTime,
  reason:     "on_demand" | "inactivity"
}
```

**`gamers` new field:** `pool_release_count: int` (default 0). When >= 5, gamer cannot pick new accounts.

**`accounts` new status:** `finished` — permanent close. New fields: `finished_at`, `finished_by` (support tg id), `final_tower_points`.

---

## Google Sheets column layout (0-indexed)

| Index | Content | Sync action |
|---|---|---|
| 0 | Profile | Identity key |
| 1 | Login | Updated |
| 2 | Password | Updated |
| 3 | Proxy | Updated; `#N/A` → skip row |
| 4 | Old Gamer (S1) | **Ignored** |
| 5 | Active | `#N/A` → skip row |
| 6 | Gamer (S3 column) | **Ignored** (Option C) |
| 7 | TP Start (`points;rank;floor`) | Seed `progress_history[0]` for new accounts only |
| 8+ | Daily sync columns (same format) | Delta calculation |

See [[flows/sheet-sync]] for full sync sequence.
