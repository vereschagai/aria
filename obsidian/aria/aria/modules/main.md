# Module: main.py

**Type:** Entry point  
**Lines:** 924  
**Role:** Registers all aiogram handlers, wires all components, runs the bot.

## Responsibilities

- Instantiates [[modules/mongodb]], [[modules/google_api]], [[modules/sheet_synchonizer]], [[modules/progress_monitor]], [[modules/operator_controller]]
- Runs `init()` on startup: `ensure_indexes()`, seed superadmins, seed config defaults
- Registers all `MessageHandler` and `CallbackQueryHandler` entries for every role and state
- Global error handler (`@dp.errors_handler`) swallows all unhandled exceptions and logs them

## Role Resolution (on /start)

```
superadmin → admin → operator → support → gamer → newcomer (referral required)
```

Handled in `start()`. Back/cancel from any FSM state also routes here.

## Handler Groups

| Group | Key handlers |
|---|---|
| Superadmin | `superadmin_grab_accounts`, `superadmin_configuration`, `superadmin_edit_configuration`, `superadmin_edit_value_configuration`, `superadmin_feed`, `superadmin_feed_send` |
| Admin/role mgmt | `admin_add`, `admin_added`, `admin_remove`, `admin_remove_confirm`, `admin_remove_confirmed` |
| Gamer | `gamer_referral_link`, `gamer_account`, `gamer_add_address`, `gamer_new_address`, `gamer_pickup_account`, `gamer_release_account_prompt`, `gamer_release_account_select` |
| Support decisions | `support_release_decision`, `support_decision` |
| Proof catch-all | `gamer_proof_submission` |

## Key Flows Handled

- [[flows/sheet-sync]] — superadmin triggers sync
- [[flows/gamer-pickup]] — `gamer_pickup_account()`
- [[flows/on-demand-release]] — `gamer_release_account_prompt()` → `gamer_release_account_select()` → `support_release_decision()`
- [[flows/inactivity-escalation]] — `support_decision()` handles resolution
- [[flows/role-management]] — `admin_add()` → `admin_added()` → `admin_remove_confirm()`

## Dependencies

- [[modules/mongodb]] — all DB calls
- [[modules/sheet_synchonizer]] — `grab_accounts()`
- [[modules/progress_monitor]] — called indirectly via synchonizer
- [[modules/operator_controller]] — `OperatorController.main()`
- [[modules/state]] — all FSM state references
- [[modules/buttons]] — all `Text(equals=...)` filter args
- [[modules/texts]] — all message strings
- [[modules/markups]] — all keyboard layouts
- [[modules/utils]] — `escape()`, `clean_messages()`, `add_message_history()`
- [[modules/google_api]] — passed to synchonizer

## Known Issues / Tech Debt

- Bot token hardcoded as fallback on line 30 — **fixed in code review**
- Superadmin Telegram ID hardcoded (seeded to DB on startup — by design, but not configurable without code change)
- Google Sheet ID hardcoded on line 49
- No automated tests
