# Flow: On-Demand Account Release

**Trigger:** "🔓 Освободить аккаунт" button in `TelegramState.start`  
**Actor:** Gamer (request) → Support (decision)  
**Handlers:** `gamer_release_account_prompt()` (line 649), `gamer_release_account_select()` (line 686), `support_release_decision()` (line 767)

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
     send texts.gamer_release_account_no_accounts
     clean_messages, add_message_history
     return
        ↓
4. Build InlineKeyboardMarkup:
   Per releasable account:
     label = profile + tower.points + last delta
     callback_data = "release_select:<account_oid_hex>"  ← 24-char hex, stays under 64-byte limit
   + back button (callback_data = "release_back")

   TelegramState.gamer_release_account.set()
   send texts.gamer_release_account_prompt + inline keyboard (MarkdownV2)
   clean_messages, add_message_history
        ↓
5a. Gamer taps back:
    gamer_release_account_select() detects "release_back"
    TelegramState.start.set() → send gamer home

5b. Gamer taps an account:
    gamer_release_account_select() fires
        ↓
6. db.get_gamer(callback_query.from_user.id) → verify gamer
   db.get_account_by_object_id(ObjectId(oid)) → verify account exists
        ↓
7. db.request_account_release(profile, gamer["_id"])
   Atomic update:
     WHERE profile == X AND gamer_id == this_gamer AND status == "active"
     $set: {status: "pending_release", release_request: {type, requested_at, gamer_id}}
   If modified_count == 0:
     account changed status between prompt and tap
     callback_query.answer("Аккаунт уже изменил статус") → TelegramState.start.set()
     return
        ↓
8. Re-fetch account for display
   Build last-5 progress_history summary
   Build release notification text (texts.support_release_request)

   Build InlineKeyboardMarkup:
     [✅ Одобрить | callback: release_approve:<oid>]
     [❌ Отклонить | callback: release_deny:<oid>]

   db.get_support_users()
   For each support user:
     send notification + inline keyboard (MarkdownV2)
     errors caught per-user (try/except, logged, continue)
        ↓
9. callback_query.answer("")
   TelegramState.start.set()
   send texts.gamer_release_account_sent.format(profile) + markups.start (MarkdownV2)
```

## Part 2 — Support Decision

```
Support taps ✅ "Одобрить":
  support_release_decision() fires (state="*")
  db.is_support(from_user.id) → if not: answer "Нет доступа", return
  db.get_account_by_object_id(oid) → if not found or status != "pending_release":
    answer "Запрос уже обработан", return

  db.release_account(profile, "released", released_at=now)
    → closes ownership_history entry, clears gamer_id,
      sets status="released", $unsets pending_proof + release_request

  if gamer has Telegram id:
    send texts.gamer_release_account_approved.format(profile) to gamer
  callback_query.answer("")
  send texts.support_release_decision_done.format(profile) to support user

Support taps ❌ "Отклонить":
  same verification steps
  db.set_account_status(profile, "active", extra_fields={"release_request": None})
    → revert to active, unset release_request
  if gamer has Telegram id:
    send texts.gamer_release_account_denied.format(profile) to gamer
  send texts.support_release_decision_done to support user
```

## End State

- Approved: account `released` (back in pool, available via [[flows/gamer-pickup]]). Gamer can immediately request a new account.
- Denied: account back to `active`. Gamer notified.

## Key Invariants

- Only `active` accounts are offered — `escalated` and `pending_release` are excluded from the prompt list
- `pending_release` counts toward slot limit but is exempt from progress check in eligibility
- Account ObjectId used in callback_data — not profile name — to stay within Telegram's 64-byte limit (see [[DECISIONS]])
- Atomic update with `status == "active"` guard prevents stale selections
- Second support user clicking a resolved request gets "already processed"

## Modules

- [[modules/main]] — all handlers
- [[modules/mongodb]] — `get_gamer`, `get_gamer_accounts`, `request_account_release`, `get_account_by_object_id`, `release_account`, `set_account_status`, `get_support_users`, `is_support`
- [[modules/texts]] — all release flow strings
- [[modules/state]] — `TelegramState.gamer_release_account`
- [[modules/utils]] — `escape`, `clean_messages`, `add_message_history`
