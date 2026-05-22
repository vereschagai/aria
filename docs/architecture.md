# Architecture

## Overview

Aria is a Telegram bot for a play-to-earn gaming guild (Goldalf Guild, game: Aria). It automates member management, game account distribution, leaderboard tracking, and crypto payout coordination.

```
┌──────────────────────────────────────────────────────────────────┐
│                          Telegram                                │
│   Users interact via keyboard buttons, inline buttons,           │
│   phone contact shares, and /start deep-links                    │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTPS (polling)
┌──────────────────────────▼───────────────────────────────────────┐
│                      aiogram 2.x bot                             │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                      main.py                                │ │
│  │  Dispatcher (dp) — registers all message/callback handlers  │ │
│  │  FSM state machine — stored in MongoStorage                 │ │
│  └────────┬────────────────────────────┬────────────────────────┘ │
│           │                            │                          │
│  ┌────────▼────────┐        ┌──────────▼──────────┐              │
│  │ operator_       │        │      MongoDb         │              │
│  │ controller.py   │        │  (motor async        │              │
│  │                 │        │   driver)            │              │
│  │ • leaderboard   │        └──────────┬───────────┘              │
│  │ • role routing  │                   │                          │
│  └─────────────────┘        ┌──────────▼───────────┐              │
│                             │      MongoDB          │              │
│  ┌──────────────────┐       │  admin / operators /  │              │
│  │  google_api.py   │       │  gamers / accounts /  │              │
│  │  GoogleSheets    │       │  config / messages    │              │
│  └────────┬─────────┘       └───────────────────────┘              │
│           │                                                       │
│  ┌────────▼──────────────┐                                        │
│  │ sheet_synchonizer.py  │                                        │
│  │ GoogleSheetSynchonizer│                                        │
│  │ (manual trigger)      │                                        │
│  └───────────────────────┘                                        │
└──────────────────────────────────────────────────────────────────┘
```

## Request lifecycle

1. User sends a message or taps a button in Telegram.
2. aiogram `Dispatcher` matches the update against registered handlers by `state` + `Text(equals=...)` filter.
3. Handler resolves user role via `MongoDb.is_superadmin/is_admin/is_operator/is_gamer`.
4. Handler reads/writes data via `MongoDb` methods.
5. Response is sent via `bot.send_message` wrapped in `utils.safe_wrap`.
6. Previous messages on screen are deleted via `utils.clean_messages`.
7. FSM state is transitioned via `TelegramState.<state>.set()`.

## Technology choices

| Concern | Choice | Why |
|---|---|---|
| Bot framework | aiogram 2.x | Mature async framework with FSM built-in |
| FSM storage | MongoStorage (aiogram contrib) | Persistent across restarts; avoids Redis dependency |
| Database | MongoDB (Motor async) | Flexible schema; natural fit for Telegram user documents |
| Retry logic | tenacity | Handles Telegram API transient 429/5xx errors |
| Sheets access | google-api-python-client | Official library; service account auth |
| Address validation | cryptoaddress | Validates BSC (EVM) wallet addresses |
| Process management | PM2 | Auto-restart, log management, multi-env deploy |

## Sequence: new gamer onboarding

```
User → /start?start=<referrer_id>
  → start() handler
  → db.is_gamer(id)? No
  → db.is_gamer(username)? No
  → newcomer = True
  → validate referral ID (must be existing member, not self)
  → has Telegram username?
      No  → store referral in FSM state, ask to set username
      Yes → db.add_gamer(id, username, referral)
           → TelegramState.start.set()
           → show gamer home screen
```

## Sequence: account sync (Google Sheets → MongoDB)

```
Superadmin → "Акки на базу" button
  → superadmin_grab_accounts() handler
  → GoogleSheetSynchonizer.grab_accounts()
  → GoogleSheets.get_accounts()  [HTTP to Google Sheets API]
  → for each row:
      parse profile, login, password, proxy, gamer, points
      db.put_account(profile, data)  [upsert by profile]
  → reply "Аккаунты успешно добавлены в базу!"
```

## Sequence: leaderboard display

```
Any user → "🏆 Лидерборд" button
  → OperatorController.__leaderboard()
  → db.get_accounts({ points.points: { $gt: 0 } })
  → aggregate: sum points per gamer username
  → sort descending
  → if gamer: find their rank, show ±leaderboard_gap rows
  → if non-gamer: show all rows
  → send MarkdownV2 message with spoiler tags on higher-ranked usernames
```

## Deployment flow

```
Local: npm run deploy-prod
  → pm2 deploy: SSH to server → git pull origin/main
  → pip install -r requirements.txt
  → pm2 reload deployment.config.js --env production --force
  → pm2 restarts aria-telegram-bot-production process
```
