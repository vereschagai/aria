# Architecture

## Overview

Aria is a Telegram bot for a play-to-earn gaming guild (Goldalf Guild, game: Aria AI). It automates member management, game account distribution, inactivity monitoring, support escalation, leaderboard tracking, and crypto payout coordination.

```
┌────────────────────────────────────────────────────────────────────┐
│                           Telegram                                 │
│   Users interact via keyboard buttons, inline buttons,             │
│   phone contact shares, and /start deep-links                      │
└────────────────────────────┬───────────────────────────────────────┘
                             │ HTTPS long-polling
┌────────────────────────────▼───────────────────────────────────────┐
│                        aiogram 2.x bot                             │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                         main.py                               │ │
│  │  Dispatcher — registers all message/callback handlers         │ │
│  │  FSM state machine — stored in MongoStorage (MongoDB)         │ │
│  │  Global @dp.errors_handler — logs and suppresses exceptions   │ │
│  └────────┬──────────────────────────┬────────────────────────────┘ │
│           │                          │                              │
│  ┌────────▼──────────┐    ┌──────────▼──────────┐                  │
│  │ operator_         │    │      MongoDb          │                  │
│  │ controller.py     │    │  (Motor async driver) │                  │
│  │                   │    └──────────┬────────────┘                  │
│  │ • Season 3        │               │                              │
│  │   leaderboard     │    ┌──────────▼────────────┐                  │
│  │ • role routing    │    │       MongoDB           │                  │
│  └───────────────────┘    │  admin / operators /   │                  │
│                           │  support / gamers /    │                  │
│  ┌───────────────────┐    │  accounts / config /   │                  │
│  │  google_api.py    │    │  messages              │                  │
│  │  GoogleSheets     │    └────────────────────────┘                  │
│  └────────┬──────────┘                                              │
│           │                                                         │
│  ┌────────▼──────────────────────┐                                  │
│  │  sheet_synchonizer.py         │                                  │
│  │  GoogleSheetSynchonizer       │                                  │
│  │  (manual trigger by superadmin│                                  │
│  │   via "Акки на базу")         │                                  │
│  └────────┬──────────────────────┘                                  │
│           │ after every sync                                        │
│  ┌────────▼──────────────────────┐                                  │
│  │  progress_monitor.py          │                                  │
│  │  ProgressMonitor              │                                  │
│  │  (inactivity checks +         │                                  │
│  │   support escalation)         │                                  │
│  └───────────────────────────────┘                                  │
└────────────────────────────────────────────────────────────────────┘
```

## Request lifecycle

1. User sends a message or taps a button in Telegram.
2. aiogram `Dispatcher` matches the update against registered handlers by `state` + `Text(equals=...)` or lambda filters.
3. Handler resolves user role via `MongoDb.is_superadmin / is_admin / is_operator / is_support`.
4. Handler reads/writes data via `MongoDb` methods.
5. Response is sent via `bot.send_message` wrapped in `utils.safe_wrap` (tenacity retry).
6. Previous messages are deleted via `utils.clean_messages`.
7. FSM state is transitioned via `TelegramState.<state>.set()`.
8. If an unhandled exception occurs, `@dp.errors_handler` logs it and returns `True` to suppress.

## Technology choices

| Concern | Choice | Why |
|---|---|---|
| Bot framework | aiogram 2.x | Mature async framework with FSM built-in |
| FSM storage | MongoStorage (aiogram contrib) | Persistent across restarts; avoids Redis dependency |
| Database | MongoDB (Motor async) | Flexible schema; natural fit for Telegram user documents |
| Retry logic | tenacity | Handles Telegram API transient 429/5xx errors |
| Sheets access | google-api-python-client | Official library; service account auth |
| Address validation | cryptoaddress 0.2.1 | Validates BSC (EVM) wallet addresses |
| Process management | PM2 | Auto-restart, log management, multi-env deploy |

## Key design decisions

### Option C — DB-only assignment

Game account assignment (`gamer_id`, `ownership_history`) is managed exclusively in MongoDB by operators. The Google Sheet column for gamer assignment (col 6) is ignored by the synchonizer. This decouples sheet management from ownership tracking and prevents sync races.

### Season 3 scoring

Points are not stored on the gamer document. They are computed live via MongoDB aggregation over `accounts.progress_history` entries where `gamer_id == gamer._id` and `delta > 0`. This means a gamer keeps all points earned on an account even after releasing it, and the score is always accurate.

### ObjectId in callback_data

Telegram limits `callback_data` to 64 bytes. Profile names can exceed this. All inline keyboard callbacks use the account's MongoDB `_id` as a 24-char hex string. Handlers look up the account by `_id` using `db.get_account_by_object_id()`.

### Calendar-day inactivity

Inactivity is measured in UTC calendar days (`(today - baseline.date()).days`), not elapsed hours. This gives consistent "1 day" / "2 days" semantics regardless of time-of-day.

## Sequence: sheet sync (current implementation)

```
Superadmin → "Акки на базу"
  → GoogleSheetSynchonizer.grab_accounts()
  → GoogleSheets.get_accounts()           [HTTP to Google Sheets API]
  → for each row:
      skip if: profile missing, row < 6 cols, col[5]==#N/A, col[3]==#N/A
      if NEW account:
          insert_one with all Season 3 fields initialised
          season3_start_points = col[7] tower points
          gamer_id = null
      if EXISTING account:
          compute delta = new_tower_points - prev_tower_points
          $set: profile, login, password, proxy, tower, last_synced_at
          if delta >= min_progress_points: $set last_progress_at
          $push progress_history entry
          (gamer_id / ownership NEVER touched)
  → ProgressMonitor.check_all()
      for each status=active account with gamer_id:
          compute days_inactive (calendar days UTC)
          if >= inactivity_escalation_days: escalate to support
          elif >= 1 day: warn gamer (once per day)
```

## Sequence: leaderboard display (Season 3)

```
Any role → "🏆 Лидерборд"
  → OperatorController.__leaderboard()
  → db.get_all_gamers_season_points()     [single aggregation]
      unwind progress_history
      match delta > 0 and gamer_id != null
      group by gamer_id, sum delta
      sort descending
  → resolve each gamer_id → username via db.get_gamer_by_id()
  → if requesting user is a gamer:
      find their rank, show ±leaderboard_gap rows
      show "||Перефарми меня||" spoiler for higher-ranked gamers
  → if non-gamer: show full list
```

## Sequence: new gamer onboarding

```
User → /start?start=<referrer_id>
  → start() handler
  → db.is_gamer(id)? No → db.is_gamer(username)? No
  → newcomer = True
  → validate referral (must be existing member, not self)
  → has Telegram username?
      No  → store referral in FSM state, show "set a username" message
      Yes → db.add_gamer(id, username, referral)
           → TelegramState.start.set()
           → show gamer home screen
```

## Deployment flow

```
npm run deploy-prod
  → pm2 deploy: SSH to production server
  → git pull origin/main
  → pip3 install -r requirements.txt
  → pm2 reload deployment.config.js --env production --force
  → process aria-telegram-bot-production restarts

npm run rollback-prod
  → pm2 deploy: SSH to server
  → git reset --hard HEAD~1
  → pip3 install -r requirements.txt
  → pm2 reload --env production --force
```
