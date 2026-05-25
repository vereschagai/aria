# Aria — What Is Implemented

Status of what is actually built and present in the codebase.

---

## Infrastructure & Bootstrap

- **`main.py::init()`** — runs at startup: calls `db.ensure_indexes()`, seeds superadmin from hardcoded list, syncs `config.py` defaults to MongoDB `config` collection.
- **`mongodb.py::ensure_indexes()`** — creates all indexes on startup: `admin(id, superadmin)`, `operators(id unique)`, `support(id unique)`, `gamers(id unique, username sparse, referral, season_picked_up sparse)`, `accounts(profile unique, gamer_id, status, last_progress_at, tower.points, progress_history.gamer_id, ownership_history.gamer_id)`, `messages(id unique)`.
- **`utils.py::safe_wrap()`** — tenacity retry wrapper (exponential backoff 1–60s) applied to all Telegram API calls.
- **`utils.py::add_message_history()` / `clean_messages()`** — message tracking and bulk deletion on screen transitions.
- **`utils.py::escape()`** — MarkdownV2 special character escaping for dynamic content.
- **Global error handler** — `@dp.errors_handler()` in `main.py` catches all unhandled exceptions, logs with `traceback`, returns `True` to keep polling alive.

---

## Role Resolution

- **`main.py::start()`** — resolves role on every `/start` command and back-navigation. Sequential checks: `is_superadmin → is_admin → is_operator → is_support → is_gamer → invite check`.
- **`OperatorController.main()`** — mirrors `start()` for role-routing in the operator controller. Routes support to `TelegramState.support_start`.
- Uninvited users (no matching role and no referral) see a "not invited" message.

---

## Superadmin Flow

All handlers registered in `main.py` on `TelegramState.superadmin_start`.

- Add admin: `admin_add()` / `admin_added()` — contact-based, phone number stored.
- Remove admin: `admin_remove()` / `admin_remove_confirm()` / `admin_remove_confirmed()` — inline button selection with confirmation.
- Configuration: `superadmin_configuration()` / `superadmin_edit_configuration()` / `superadmin_edit_value_configuration()` — inline buttons list editable config fields; value updated in MongoDB.
- Broadcast: `superadmin_feed()` / `superadmin_feed_send()` — sends message to all gamers.
- Sheet sync: `superadmin_grab_accounts()` — calls `synchonizer.grab_accounts()`, which triggers `ProgressMonitor.check_all()` after completion.

---

## Admin Flow

All handlers registered in `main.py` on `TelegramState.admin_start`.

- Add operator: contact-based via `admin_add()` on `admin_add_operator` state.
- Add support: contact-based via `admin_add()` on `admin_add_support` state (dedicated state, does not collide with operator add).
- Remove operator/support: inline button selection with confirmation, shared handler pattern.
- Error handler: `admin_added_error()` — shows correct role name in error message for both operator and support add states.

---

## Operator Flow

- `TelegramState.operator_start` — routes to leaderboard via `OperatorController`.
- No account management — operators no longer assign accounts (Season 4: fully automated).

---

## Support Flow

- `TelegramState.support_start` — support users see leaderboard button.
- **Escalation receive**: `ProgressMonitor._escalate()` sends support users a case card with last 5 progress history entries and two inline buttons: "✅ Прогресс возможен" / "❌ Прогресс невозможен".
- **`support_decision()`** in `main.py` — handles `support_progress:` and `support_noprogress:` callback data. Resolves account by ObjectId. Progress possible → `release_account(profile, "released")` + notifies gamer with `gamer_account_released` text. No progress → `release_account(profile, "inactive")` + notifies gamer with `gamer_account_inactive` text. Either way, gamer's earned points are preserved in `progress_history`.
- **On-demand release receive**: `support_release_decision()` in `main.py` — handles `release_approve:` and `release_deny:` callback data. Approve → `release_account()` + notifies gamer. Deny → revert to `active` via `set_account_status()` + notify gamer.

---

## Gamer Flow

All handlers on `TelegramState.start`.

- **Referral**: `gamer_referral_link()` — generates and shows invite link.
- **Account screen**: `gamer_account()` — shows all accounts owned by this gamer with status emojis (`✅` active, `⚠️` escalated, `⏳` pending_release, `🔒` released/inactive), tower points, last delta, season score (from `get_gamer_season_points()`), BSC wallet address.
- **Wallet**: `gamer_add_address()` / `gamer_change_address()` / `gamer_new_address()` — validates BSC address via `cryptoaddress.EthereumAddress`.
- **Leaderboard**: accessible from `TelegramState.start` via `OperatorController.__leaderboard()`.
- **Pickup account** (`gamer_pickup_account()`):
  - Calls `check_assignment_eligibility(gamer._id, config)` — checks slot limit and ownership-gated progress condition.
  - On eligibility: calls `pickup_account(gamer._id)` — Priority 1 (own history) then Priority 2 (inactive-owner accounts), atomic `findOneAndUpdate`.
  - Returns credentials in chat if assigned, "no accounts available" otherwise.
  - Calls `mark_gamer_season_active()` on success.
- **Release account** (`gamer_release_account_prompt()` / `gamer_release_account_select()`):
  - Shows inline list of strictly `active` accounts (not escalated, not pending).
  - Selection calls `request_account_release(profile, gamer._id)` → sets `status = "pending_release"`.
  - Notifies all support users with dedicated buttons ("✅ Разрешить освобождение" / "❌ Отклонить").
  - None guard on `get_gamer()` in all four gamer handlers.
- **Proof submission** (`gamer_proof_submission()`): gamer forwards any message while on `TelegramState.start`; stored as `pending_proof` on the account via `store_proof()`.

---

## Sheet Sync (`sheet_synchonizer.py`)

- Reads `Accounts` tab, range `A2:AQ`.
- Row-level guards: skip if no profile, fewer than 6 columns, `Active == "#N/A"`, or `proxy == "#N/A"`.
- **New accounts**: inserts with `status="released"`, `gamer_id=null`, seed `progress_history` entry (delta = tp_start from col 7), `ownership_history=[]`.
- **Existing accounts**: computes delta (`new_points - history[-1].tower_points`), pushes `progress_history` entry with snapshot of current `gamer_id`. Updates `last_progress_at` only if `delta >= min_progress_points`. Never touches `gamer_id` or `ownership_history` (Option C).
- `__parse_tower()`: handles `NaN`, empty strings, floats, missing indices — always returns safe zeros.
- `get_config()` fetched once before the loop (not per row).
- Triggers `ProgressMonitor.check_all()` after all rows processed.

---

## Inactivity Monitor (`progress_monitor.py`)

- `check_all()` — iterates all `status=active` accounts with a `gamer_id`.
- Baseline: `last_progress_at` if set, else `ownership_history[-1].assigned_at`.
- `days_inactive = (today_utc - baseline.date()).days` — calendar days, UTC.
- Deduplication: skips if `last_notified_day == today_ordinal`.
- Day 1+: calls `_warn_gamer()` — sends `gamer_inactivity_warning` text to gamer. Updates `last_notified_day`.
- Day N (`inactivity_escalation_days`, default 3): calls `_escalate()` — sets status to `"escalated"`, sends case card to all support users, notifies gamer. Already-escalated accounts are not re-escalated or warned.
- `_escalate()` uses ObjectId hex in `callback_data` (24 chars, within Telegram 64-byte limit).

---

## Leaderboard

- `OperatorController.__leaderboard()` — accessible from `operator_start`, `support_start`, `superadmin_start`, `admin_start`, `start` states.
- Calls `get_all_gamers_season_points()` (one aggregation over `accounts.progress_history`).
- Batch-resolves ObjectIds to usernames: `gamers.find({_id: {$in: oids}})` — total 2 queries.
- Renders gamer's position with `leaderboard_gap` rows above/below (config, default 4). Shows `...` when truncated.
- Own position bolded. Users below the requesting gamer see spoiler text "||Перефарми меня||".

---

## MongoDB Methods Implemented

**Config**: `get_config`, `update_config`  
**Admins**: `is_superadmin`, `add_superadmin`, `get_admins`, `is_admin`, `get_admin`, `add_admin`, `remove_admin`  
**Operators**: `get_operators`, `is_operator`, `get_operator`, `add_operator`, `remove_operator`  
**Support**: `get_support_users`, `is_support`, `get_support_user`, `add_support`, `remove_support`  
**Gamers**: `is_gamer`, `get_gamer`, `get_gamer_by_id`, `add_gamer`, `update_gamer`, `update_gamer_address`, `get_all_gamers_season_points`, `get_gamer_season_points`, `mark_gamer_season_active`  
**Accounts**: `get_accounts`, `get_account`, `get_account_by_object_id`, `put_account`, `push_progress_entry`, `get_gamer_accounts`, `get_active_assigned_accounts`, `get_escalated_accounts`, `set_account_status`, `release_account`, `store_proof`, `request_account_release`, `check_assignment_eligibility`, `pickup_account`  
**Messages**: `push_message_history`, `get_message_history`, `clean_message_history`  
**Indexes**: `ensure_indexes`

---

## Migrations

- **`migration_season3.py`** — seeds `season3_start_points`, wires `gamer_id` from sheet username lookup, initialises `ownership_history`, creates stub gamer records for unresolved sheet usernames. **Already applied on production.**
- **`migration_season4.py`** — prepends seed `progress_history` entry (delta = `season3_start_points`), closes open ownership entries, strips `gamer_username` from ownership history, sets `status="released"` / `gamer_id=null`, unsets `season3_start_points`, `available_for_pickup`, `gamer`, `pending_proof`, `release_request`. Idempotent (skips accounts without `season3_start_points`). **Status: written, not yet applied on production.**

---

## Deployment Scripts (`package.json`)

- `deploy-prod` / `deploy-qa` — git pull + pip install + pm2 reload
- `rollback-prod` / `rollback-qa` — git reset --hard HEAD~1 + pip install + pm2 reload
- `logs-prod` / `error-logs-prod` / `logs-qa` / `error-logs-qa` — tail PM2 logs

---

## Known Gaps (intentional or deferred)

| # | Gap | Notes |
|---|---|---|
| 1 | `inactivity_day_buffer_hours` config field is dead | Kept for DB compat; not read at runtime |
| 2 | Support home has no "active escalations" list | Not yet implemented |
| 3 | Sheet sync is manual | Automation (Octo+Puppeteer on Windows) is a parallel project |
| 4 | No automated tests | Test strategy TBD |
| 5 | `client_secret.json` is committed to git | Security risk; needs rotation and .gitignore |
| 6 | Bot token hardcoded as fallback in `main.py` | Should be removed or replaced with invalid placeholder |
| 7 | `main.py` is 924 lines — all handlers in one file | Phase 3 refactor: split into controller modules |
| 8 | aiogram 2.x is EOL | Migration to v3 is a breaking rewrite |
| 9 | `season_picked_up` not reset between seasons | Must be `$unset` in future `migration_season5.py` |
