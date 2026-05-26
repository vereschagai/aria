# Flow: On-Demand Account Release (Redesigned — Sprint E)

**Trigger:** "🔓 Освободить аккаунт" button in `TelegramState.start`
**Actor:** Gamer (request) → Support (decision)
**Handlers:** `gamer_release_account_prompt()`, `gamer_release_account_select()`, `support_release_decision()`

---

## Part 1 — Gamer Requests Release

```
1. Gamer presses "🔓 Освободить аккаунт"
       ↓
2. db.get_gamer(user_id) → if None, return
   db.get_gamer_accounts(gamer["_id"]) → all accounts for this gamer
   releasable = [a for a in accounts if a["status"] == "active"]
       ↓
3. add_message_history

   If no releasable accounts:
     send texts.gamer_release_account_no_accounts + markups.start
     clean_messages, add_message_history
     return
       ↓
4. Build InlineKeyboardMarkup:
   Per releasable account:
     label = profile + tower.points + last delta (gamer's own entries only)
     callback_data = "release_select:<account_oid_hex>"
   + back button (callback_data = "release_back")

   TelegramState.gamer_release_account.set()
   send texts.gamer_release_account_prompt + inline keyboard (MarkdownV2)
   clean_messages, add_message_history
       ↓
5a. Gamer taps back → TelegramState.start.set() → send gamer home

5b. Gamer taps an account → gamer_release_account_select() fires
       ↓
6. Verify gamer and account exist in DB
       ↓
7. db.request_account_release(profile, gamer["_id"])
   Atomic: WHERE profile==X AND gamer_id==this_gamer AND status=="active"
   $set: {status: "pending_release", release_request: {type: "on_demand", requested_at, gamer_id}}
   If modified_count == 0 → answer "Аккаунт уже изменил статус", TelegramState.start.set(), return
       ↓
8. TRIGGER EXPLICIT SYNC: synchonizer.sync_single_account(profile)
   Ensures gamer's last session points are captured before ownership ends.
       ↓
9. Re-fetch account
   Build progress history — FILTER: only entries where entry.gamer_id == gamer["_id"]
   Show last 5 of gamer's own entries

   Build release notification (texts.support_release_request)

   Build InlineKeyboardMarkup for support — ON-DEMAND TYPE → 3 buttons:
     [🔓 В пул          | callback: release_pool:<oid>]
     [🚫 Закрыть навсегда | callback: release_finish:<oid>]
     [↩️ Отклонить      | callback: release_deny:<oid>]

   db.get_support_users() → fan-out notification to all support users
       ↓
10. callback_query.answer("")  ← called FIRST (at top of handler)
    TelegramState.start.set()
    send texts.gamer_release_account_sent.format(profile) + markups.start
```

---

## Part 2 — Support Decision

### "🔓 В пул" (release_pool:\<oid\>) — release to shared pool
```
1. Verify: account status must be "pending_release" OR "escalated"
2. db.add_release_block(account_id, gamer_id, reason)  ← gamer cannot repick this account EVER
3. db.increment_pool_release_count(gamer_id)
   If new count >= 5: send gamer one-time ban notification
4. db.release_account(profile, "released", released_at=now)
   → closes ownership_history entry, clears gamer_id, unsets release_request
5. Notify gamer: texts.gamer_release_account_pool_approved.format(profile)
6. Notify support: texts.support_release_decision_done.format(profile)
```

### "🚫 Закрыть навсегда" (release_finish:\<oid\>)
```
1. Verify: account status must be "pending_release" OR "escalated"
2. db.finish_account(profile, support_id=from_user.id, now=now)
   → status="finished", finished_at=now, finished_by=support_tg_id,
     final_tower_points=account["tower"]["points"]
3. Notify gamer: texts.gamer_release_account_finished.format(profile)
4. Notify support: texts.support_release_decision_done.format(profile)
```

### "↩️ Отклонить" (release_deny:\<oid\>) — ON-DEMAND ONLY, not shown for inactivity
```
1. Verify: account status must be "pending_release"
2. db.set_account_status(profile, "active", extra_fields={"release_request": None})
3. Notify gamer: texts.gamer_release_account_denied.format(profile)
4. Notify support: texts.support_release_decision_done.format(profile)
```

---

## Account Status Lifecycle

```
released → (pickup) → active → (gamer 🔓) → pending_release → (support: 🔓 В пул)       → released  [+block, +count]
                                                              → (support: 🚫 Закрыть)     → finished
                                                              → (support: ↩️ Отклонить)   → active     [on-demand only]
                             → (inactivity) → escalated     → (support: 🔓 В пул)        → released  [+block, +count]
                                                              → (support: 🚫 Закрыть)     → finished
```

---

## Gamer Ban Logic

- Field: `gamers.pool_release_count` (counts both on-demand AND inactivity releases to pool)
- When count >= 5: gamer CANNOT pick new accounts (blocked in eligibility check)
- Gamer CAN still: play remaining active accounts, release them, view leaderboard
- Ban message: "Вы освободили слишком много аккаунтов. Взять новый нельзя."
- Ban is permanent for the season

---

## Account-Gamer Block

- Collection: `release_blocks { account_id: ObjectId, gamer_id: ObjectId, blocked_at, reason }`
- Index: compound unique `(account_id, gamer_id)`
- Effect: blocked gamer cannot pick that account again even if another gamer also releases it
- Applied in `pickup_account` query: excluded from P1 and P2 candidate pools via `$nin`

---

## Finished Accounts

- Status: `finished` — permanent, no one can pick
- Fields: `finished_at`, `finished_by` (support tg id), `final_tower_points`
- Visible in: superadmin and support "📋 Закрытые аккаунты" list
- List shows: profile name | last gamer username | closed date | tower points at close

---

## Progress History Filter

In all release notification messages (gamer-initiated AND inactivity):
- Show only `progress_history` entries where `entry.gamer_id == gamer._id`
- Show last 5 of the gamer's own entries (not global account history)

---

## Key Invariants

- `callback_query.answer("")` called FIRST in `gamer_release_account_select` before any DB work
- Deny button (`release_deny`) only present when `release_request.type == "on_demand"`
- Inactivity escalation buttons: only `release_pool` + `release_finish` (no deny)
- All dynamic values in MarkdownV2 messages go through `utils.escape()`
- Lambda closures in support fan-out loop: `lambda su=su:` to capture by value

## Modules

- [[modules/main]] — all handlers
- [[modules/mongodb]] — `get_gamer`, `get_gamer_accounts`, `request_account_release`,
  `get_account_by_object_id`, `release_account`, `set_account_status`, `get_support_users`,
  `is_support`, `add_release_block`, `increment_pool_release_count`, `finish_account`,
  `get_finished_accounts`
- [[modules/texts]] — all release flow strings
- [[modules/state]] — `TelegramState.gamer_release_account`
- [[modules/utils]] — `escape`, `clean_messages`, `add_message_history`
- [[modules/sheet_synchonizer]] — `sync_single_account(profile)` (new)
