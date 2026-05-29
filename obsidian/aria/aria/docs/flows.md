# User Flows

All conversation flows in the Aria Telegram bot. Each flow is described by: entry trigger, state transitions, DB operations, and messages sent.

For the full FSM state map see CLAUDE.md in the codebase. For data model see [[data-model]].

---

## Role resolution (`/start`)

**Trigger:** `/start` command from any state, or pressing a Back button from most screens.

**Handler:** `main.py::start()`

```
Incoming user
    │
    ├── is_superadmin? ──▶ superadmin_start  (texts.superadmin_start, markups.superadmin_start)
    │
    ├── is_admin? ──────▶ admin_start        (texts.admin_start, markups.admin_start)
    │
    ├── is_operator? ───▶ OperatorController.main()  (see Operator flow)
    │
    ├── is_support? ────▶ support_start      (texts.support_start_text, markups.support_start)
    │
    └── else (gamer path)
            │
            ├── existing gamer by id or username ──▶ start state (gamer home)
            │
            └── newcomer
                    │
                    ├── no referral link ──▶ texts.gamer_only_invite_access
                    ├── no username ───────▶ texts.gamer_no_username
                    └── valid referral ────▶ add_gamer() + start state (gamer home)
```

---

## Superadmin flows

### Add admin
`superadmin_start` → tap "Добавить админа" → `superadmin_add_admin`
- Bot asks for phone contact
- On contact received: `db.add_admin(contact)` → back to `superadmin_start`
- On non-contact: error message, stay in state

### Remove admin
`superadmin_start` → tap "Удалить админа" → `superadmin_remove_admin`
- Bot shows inline keyboard with all admins
- On selection: `superadmin_remove_admin_confirm` — asks "are you sure?"
- On confirm: `db.remove_admin()` + `state.finish()` for the removed admin → `superadmin_start`
- On back/cancel: → `superadmin_start`

### Configuration
`superadmin_start` → tap "⚙️ Конфигурация" → `superadmin_configuration`
- Bot shows inline keyboard with current config fields and values
- On field selection: `superadmin_edit_configuration` — asks for new value
- On valid value: `db.update_config(field, value)` → `superadmin_start`
- On invalid value: error message, stay in state

### Broadcast
`superadmin_start` → tap "Связь с общественностью" → `superadmin_feed`
- Bot waits for any message/media
- On message: copies it to every gamer → `superadmin_start`

### Sheet sync
`superadmin_start` → tap "Акки на базу"
- Calls `synchonizer.grab_accounts()` (sync + inactivity check)
- Reply: `texts.admin_grab_account_done`
- State stays at `superadmin_start`

---

## Admin flows

### Add operator
`admin_start` (or `superadmin_start`) → tap "Добавить оператора" → `admin_add_operator`
- Bot asks for phone contact
- On contact: `db.add_operator(contact)` → back to start

### Add support
`admin_start` (or `superadmin_start`) → tap "Добавить поддержку" → `admin_add_support`
- Bot asks for phone contact
- On contact: `db.add_support(contact)` → back to start

### Remove operator / Remove support
Mirror of the Remove admin flow above, using `admin_remove_operator` / `support_remove` states.

---

## Operator flow

`OperatorController.main(user_id)` is called from `start()` when role = operator.
The operator home screen (`operator_start`) currently only shows the Leaderboard button.

---

## Support flow

Support users receive **push notifications** for two event types:
1. **Inactivity escalation** — pushed by `ProgressMonitor._escalate()`
2. **On-demand release request** — pushed by the gamer release handler in `main.py`

Both arrive as inline keyboard messages. Support does not need to navigate to any screen.

### Support home
`support_start` — shows Leaderboard button and "📋 Задачи" dashboard button.

### Support dashboard
`support_start` → tap "📋 Задачи" → `support_dashboard`
- Calls `db.get_open_support_tasks()` — returns all `escalated` + `pending_release` accounts with gamer info
- Shows paginated inline keyboard (5 tasks per page)
- Support sees action buttons (🔓 release, 🚫 finish, ↩️ deny) + 💬 DM button
- Superadmin sees DM-only view (no action buttons)
- Pagination via `dash_page:{n}` callbacks (edits message in-place)
- Back button returns to role home

---

## Leaderboard (all roles)

Accessible from: `start`, `operator_start`, `superadmin_start`, `admin_start`, `support_start`.
**Handler:** `OperatorController.__leaderboard()`

1. Calls `db.get_all_gamers_season_points()` — single aggregation returning `[{_id: gamer_oid, total: points}]`
2. Resolves each `gamer_oid` → username via `db.get_gamer_by_id()`
3. Builds text with window around the requesting gamer's rank (`leaderboard_gap` rows above/below)
4. Non-gamers (admin/operator/support) see the full list

State: → `leaderboard`. Back button returns to role home.

---

## Gamer flows

### Gamer home (`start`)

Keyboard: `👤 Мой аккаунт` | `🏆 Лидерборд` | `🎮 Взять аккаунт` | `🔓 Освободить аккаунт` | `💸 Реферальная программа`

### My account

`start` → tap "👤 Мой аккаунт" → `account`

Displays:
- Referral info
- BSC wallet address (or prompt to add one)
- Season 3 total points (live from `db.get_gamer_season_points()`)
- All assigned accounts with: status emoji, tower points, last delta, login/password, proxy

Status emojis: `active=✅`, `escalated=🚨`, `released=🔓`, `inactive=⛔`, `pending_release=⏳`

#### Add/change wallet

`account` → tap "💵 Добавить кошелек" → `address`
`account` → tap "💵 Сменить кошелек" → `change_address`

- Bot waits for BSC address text
- Validates with `EthereumAddress()` from `cryptoaddress`
- On valid: `db.update_gamer_address()` → returns to `account` screen
- On invalid: error message, stay in state

### Referral link

`start` → tap "💸 Реферальная программа" → `referral`
- Shows unique invite link: `t.me/<bot>?start=<user_id>`
- Back returns to `start`

### Pick up account (Season 4)

`start` → tap "🎮 Взять аккаунт"

1. `db.check_assignment_eligibility(gamer._id, config)` → `(eligible, reason)`
2. If not eligible: shows reason to gamer; state stays at `start`
3. If eligible: `db.pickup_account(gamer._id)` — atomic find-and-assign
4. If pool empty: shows `texts.gamer_pickup_no_accounts`; state stays at `start`
5. If assigned: `db.mark_gamer_season_active(gamer._id)` → confirms with credentials (`texts.gamer_pickup_success`)
6. State stays at `start` throughout (no intermediate FSM state)

**Eligibility rules** (both must hold):
- Occupied accounts (active + escalated + pending_release) < `max_accounts_per_gamer`
- All strictly `active` accounts: `progress_history[-1].gamer_id == this_gamer` **and** `progress_history[-1].delta >= min_progress_points` (escalated/pending_release are exempt)

**Pickup priority** (see `mongodb.pickup_account`):
1. Accounts previously owned by this gamer, sorted descending by `tower.points`
2. Accounts whose last owner has not picked up this season (`season_picked_up != true`) or has no previous owner, sorted descending by `tower.points`

Assignment is atomic — `findOneAndUpdate` with `status == "released"` guard prevents double-claiming.

### On-demand account release

`start` → tap "🔓 Освободить аккаунт" → `gamer_release_account`

1. Fetch all accounts where `gamer_id == gamer._id` and `status == "active"`
2. If none: show "no releasable accounts" message
3. If some: show inline keyboard with one button per account (label: profile + tower points + last delta)
   - `callback_data = "release_select:<account._id hex>"`
   - Back button: `callback_data = "release_back"`

On account selected:
1. `db.request_account_release(profile, gamer._id)` — sets `status = "pending_release"`
2. Fetches last 5 progress history entries
3. Builds `texts.support_release_request` message with inline keyboard:
   - ✅ Разрешить освобождение → `release_approve:<account._id hex>`
   - ❌ Отклонить → `release_deny:<account._id hex>`
   - 💬 DM → `tg://user?id={gamer_tg_id}`
4. Sends to **all support users**
5. Confirms to gamer: `texts.gamer_release_account_sent`
6. Returns gamer to `start`

**Support decision** (handled by `support_release_decision` in `main.py`, state `"*"`):
- Guard: checks `db.is_support()` and `account.status == "pending_release"`
- `release_approve`: `db.release_account(profile, "released", now)` → gamer notified
- `release_deny`: `db.set_account_status(profile, "active", {release_request: None})` → gamer notified

### Proof submission

Any message sent by a gamer in `start` state that doesn't match a button:
- Caught by `gamer_proof_submission` handler (`content_types=ANY`)
- Checks if gamer has an `escalated` account with `pending_proof: null`
- If yes: `db.store_proof()` + forwards message to all support users immediately
- Confirms to gamer: `texts.gamer_proof_received`

---

## Inactivity escalation flow

Triggered automatically after every sheet sync via `ProgressMonitor.check_all()`.

```
For each account: status=active, gamer_id != null
    │
    baseline = last_progress_at  OR  ownership_history[-1].assigned_at
    days_inactive = (today_utc - baseline.date()).days
    │
    ├── days_inactive < 1 ──▶ skip (making progress)
    │
    ├── last_notified_day == today_ordinal ──▶ skip (already notified today)
    │
    ├── days_inactive >= inactivity_escalation_days
    │   └── _escalate(account)
    │           1. set status = "escalated", escalated_at = now, last_notified_day = ordinal
    │           2. build escalation message (last 5 progress entries)
    │           3. send to all support users with inline keyboard:
    │              ✅ Прогресс возможен → support_progress:<account._id hex>
    │              ❌ Прогресс невозможен → support_noprogress:<account._id hex>
    │              💬 DM → tg://user?id={gamer_tg_id}
    │           4. forward pending_proof if any
    │           5. notify gamer: texts.gamer_escalated
    │
    └── days_inactive >= 1 (and not escalated)
        └── _warn_gamer(account, days_inactive)
                1. send texts.gamer_inactivity_warning to gamer
                2. set last_notified_day = today_ordinal
```

**Support decision** (handled by `support_decision` in `main.py`, state `"*"`):
- Guard: checks `db.is_support()` and `account.status == "escalated"`
- `support_progress`: `db.release_account(profile, "released", now)` → gamer gets `texts.gamer_account_released`
- `support_noprogress`: `db.release_account(profile, "inactive", now)` → gamer gets `texts.gamer_account_inactive`

In both cases: `db.release_account()` closes the open `ownership_history` entry and clears `gamer_id`.

---

## Sheet sync flow

**Trigger:** superadmin taps "Акки на базу"
**Handler:** `sheet_synchonizer.grab_accounts()`

```
For each row in sheet (range A2:AQ):
    │
    ├── profile missing or row < 6 cols ──▶ skip
    ├── col[5] == "#N/A" ──▶ skip (not active in S3)
    ├── col[3] == "#N/A" ──▶ skip (no proxy)
    │
    ├── account NOT in DB ──▶ insert_one with all S3 fields initialised
    │                          gamer_id = null
    │                          season3_start_points = col[7] tower points
    │                          progress_history = []
    │                          status = "active"
    │
    └── account EXISTS
            │
            prev_points = progress_history[-1].tower_points
                          OR season3_start_points (if history empty)
            delta = new_tower_points - prev_points
            │
            $set: profile, login, password, proxy, tower, last_synced_at
            if delta >= min_progress_points: $set last_progress_at = now
            $push: progress_history entry {synced_at, tower_points, delta, gamer_id}
            │
            (gamer_id and ownership_history are NEVER touched)

After all rows processed:
    └── ProgressMonitor.check_all()
```
