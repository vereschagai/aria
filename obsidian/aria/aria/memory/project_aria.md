---
name: project-aria
description: "Aria bot — full project context: what it is, stack, architecture,
  current season, deployment, and open gaps"
type: project
updated: 2026-05-26
version: "3"
---

# Aria Telegram Bot — Project Overview

**What it is:** Async Python Telegram bot automating play-to-earn account management for Goldalf Guild (game: Aria AI). Handles member management, game account distribution, inactivity monitoring, support escalation, leaderboard, and crypto payout coordination.

See [[memory/reference_aria_codebase|Codebase Reference]] for file locations, IDs, and collection schemas.
See [[memory/feedback_aria_workflow|Workflow Rules]] for required coding patterns.
See [[CONTEXT]] for full architecture detail. See [[DECISIONS]] for all 12 ADRs.

---

## Stack

| Concern | Choice |
|---|---|
| Bot framework | aiogram 2.x (EOL — v3 migration deferred, breaking rewrite) |
| FSM storage | MongoStorage (aiogram contrib) — persistent in MongoDB |
| Database | MongoDB (Motor async driver) |
| Retry | tenacity 7.0.0 — exponential backoff 1–60s |
| Sheets | google-api-python-client 2.2.0 + `client_secret.json` service account |
| Address validation | cryptoaddress 0.2.1 (BSC/EVM) |
| Process management | PM2 via `deployment.config.js` (gitignored) |
| External scraper | Octo Browser + Puppeteer — **separate project, not in this repo** |

---

## Architecture Invariants

**Option C (DB-only assignment):** Sheets is read-only. `gamer_id` and `ownership_history` are NEVER written by `GoogleSheetSynchonizer`. Sheet col 6 permanently ignored. See [[DECISIONS#Option C DB-only gamer assignment (no sheet writes)]].

**Scoring:** Season score = Σ positive `progress_history.delta` where `gamer_id == gamer._id` across ALL ever-owned accounts. One aggregation covers the full leaderboard. See [[DECISIONS#Season 3 scoring cumulative positive progress_history deltas]].

**Inactivity:** UTC calendar days `(today_utc - baseline.date()).days`. Day 1 → warn; Day N (default 3) → escalate to all support. See [[flows/inactivity-escalation]].

**ObjectId in callback_data:** Telegram 64-byte limit → always `account._id` hex (24 chars). See [[DECISIONS#ObjectId hex in Telegram callback_data]].

**Message cleanup:** Every screen transition → `add_message_history` → `clean_messages` → send → `add_message_history`.

---

## Role Hierarchy

```
superadmin → admin → operator → support → gamer
```

Resolved on every `/start` and back-navigation. See [[flows/start-role-resolution]].

---

## Module Map

| File | Lines | Purpose |
|---|---|---|
| `main.py` | 929 | All handlers, FSM, role resolution, global error handler |
| `mongodb.py` | 443 | All DB operations — `MongoDb` class |
| `sheet_synchonizer.py` | ~173 | Sheets import — never touches `gamer_id` |
| `progress_monitor.py` | ~172 | Inactivity warnings + support escalation |
| `operator_controller.py` | ~110 | Leaderboard (2 queries) + role routing |
| `state.py` | 31 | All FSM states |
| `google_api.py` | ~36 | Async Sheets wrapper — `run_in_executor` |

See [[modules/main]], [[modules/mongodb]], [[modules/sheet_synchonizer]], [[modules/progress_monitor]].

---

## Current Season State

**Season 4 is live on production.** Both `migration_season3.py` and `migration_season4.py` applied. Do not re-run either. See [[PROGRESS#Migrations]].

Key S4 changes (all live):
- Instant auto-assign replaces operator flow — see [[flows/gamer-pickup]]
- `season3_start_points` removed → seed entry in `progress_history[0]`
- `available_for_pickup` removed → `status == "released"` only
- `gamer_id` ownership guard added to eligibility check
- `season_picked_up` flag added to gamers → must `$unset` in `migration_season5.py`

---

## Account Status Lifecycle

```
released → (pickup) → active → (inactivity) → escalated → (support: ❌) → inactive
                             → (gamer 🔓) → pending_release → (support: ✅) → released
                                                            → (support: ❌) → active
```

See [[flows/on-demand-release]], [[flows/inactivity-escalation]], [[flows/gamer-pickup]].

---

## Config Defaults

| Field | Default | Notes |
|---|---|---|
| `leaderboard_gap` | 4 | Rows shown above/below requesting gamer |
| `min_progress_points` | 50 | Delta per sync for good progress |
| `max_accounts_per_gamer` | 10 | Max simultaneous accounts |
| `inactivity_escalation_days` | 3 | Calendar days before escalation |
| `support_handle` | `@goldalfsupp` | Configurable — stored in `config` collection |

---

## Environment Variables (all required — raise RuntimeError if unset)

| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `ARIA_SHEET_ID` | Google Sheets spreadsheet ID |
| `DB_HOST` / `DB_PORT` / `DB_NAME` | MongoDB connection |
| `DB_USERNAME` / `DB_PASSWORD` | MongoDB auth (optional) |

---

## Deployment

| Env | Host | DB | PM2 process |
|---|---|---|---|
| Production | `176.29.100.183:2223` | `aria` | `aria-telegram-bot-production` |
| QA | `95.111.241.149:22` | `aria_qa` | `aria-telegram-bot-qa` |

`npm run deploy-prod` — git pull + pip install + pm2 reload
`npm run rollback-prod` — git reset --hard HEAD~1 + pip install + pm2 reload

---

## Known Gaps (as of 2026-05-26)

| # | Gap | Notes |
|---|---|---|
| 1 | Support home has no "active escalations" list | Not yet implemented |
| 2 | Sheet sync is manual | Octo+Puppeteer automation is a parallel project |
| 3 | Test coverage partial | 36 pytest tests written and passing: test_progress_monitor, test_sheet_synchonizer, test_mongodb_eligibility, test_websocket_server. No handler/integration tests yet. |
| 4 | `client_secret.json` git history | ✅ Confirmed clean — never committed, properly gitignored. No action needed. |
| 5 | `main.py` is 929 lines | Phase 3 refactor planned: split into controllers |
| 6 | aiogram 2.x is EOL | v3 migration is a breaking rewrite |
| 7 | `season_picked_up` not reset between seasons | Must `$unset` in `migration_season5.py` |
| 8 | `aiocron` possibly unused | Verify if any `@cron` decorators used |
| 9 | Superadmin ID hardcoded in `main.py` | By design — requires code change to add second superadmin |

See [[REVIEW]] for full implementation gap analysis.
