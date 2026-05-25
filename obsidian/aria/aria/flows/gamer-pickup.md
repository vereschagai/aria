# Flow: Gamer Account Pickup (Season 4)

**Trigger:** "🎮 Взять аккаунт" button in `TelegramState.start`  
**Actor:** Gamer  
**Handler:** `gamer_pickup_account()` — main.py line 601

## Steps

```
1. Gamer presses "🎮 Взять аккаунт"
        ↓
2. db.get_gamer(user_id) → if None, return
   db.get_config() → read max_accounts_per_gamer, min_progress_points
        ↓
3. db.check_assignment_eligibility(gamer["_id"], config)
   Returns (bool, reason_string)

   Slot check:
     count accounts where gamer_id == oid AND status IN [active, escalated, pending_release]
     if count >= max_accounts_per_gamer:
       return (False, "Достигнут лимит аккаунтов (N)")

   Progress check (for each ACTIVE account only):
     take last progress_history entry
     if entry.gamer_id != this_gamer OR entry.delta < min_progress_points:
       return (False, "Аккаунт X — недостаточно прогресса")
     (empty progress_history → skip, newly assigned)

   return (True, "ok")
        ↓
4. add_message_history

   If NOT eligible:
     send texts.gamer_pickup_ineligible.format(reason) (MarkdownV2)
     clean_messages, add_message_history
     return (stay in TelegramState.start)
        ↓
5. db.pickup_account(gamer["_id"])
   Atomic find-one-and-update with status=="released" guard:

   Priority 1 candidates:
     status == "released" AND gamer_id appears in ownership_history[].gamer_id
     sorted by tower.points DESC

   Priority 2 candidates:
     status == "released", excluding P1 account IDs
     last ownership_history entry's gamer has season_picked_up != True
     sorted by tower.points DESC

   For each candidate in P1 then P2:
     findOneAndUpdate(
       {_id: candidate._id, status: "released"},
       {$set: {gamer_id, status:"active", last_notified_day:None, escalated_at:None},
        $push: {ownership_history: {gamer_id, assigned_at:now}}}
     ) → returns updated doc if race-safe, else None

   First successful assignment is returned.
        ↓
6. If no account found:
   send texts.gamer_pickup_no_accounts
   clean_messages, add_message_history
   return

   If account assigned:
   db.mark_gamer_season_active(gamer["_id"]) → idempotent set season_picked_up = True
   send texts.gamer_pickup_success.format(profile, login, password) (MarkdownV2)
   clean_messages, add_message_history
```

## End State

`TelegramState.start`. Gamer sees account credentials (success) or an eligibility error.

## Priority Algorithm Detail

- P1 is for returning gamers — they get their best historically-owned account first
- P2 targets accounts left by gamers who haven't picked anything this season (`season_picked_up != True`)
- If both pools are empty: "no accounts available"
- Gamer is never shown a choice — fully automatic (see [[DECISIONS]])

## Eligibility Edge Cases

- Accounts with empty `progress_history`: skipped in progress check (newly assigned, no data yet)
- `pending_release` accounts: count toward slot limit, excluded from progress check
- `escalated` accounts: count toward slot limit, do NOT block eligibility (see [[DECISIONS]])
- The 1-sync delay: right after pickup, `progress_history[-1].gamer_id` still belongs to the previous owner → progress check blocks until next sync runs under new owner's ownership

## Race Condition Protection

`findOneAndUpdate` with `status == "released"` guard prevents two gamers from getting the same account. Eligibility check is NOT atomic with pickup — if the last account is taken between step 3 and step 5, gamer gets "no accounts" message.

## Modules

- [[modules/main]] — handler
- [[modules/mongodb]] — `get_gamer`, `get_config`, `check_assignment_eligibility`, `pickup_account`, `mark_gamer_season_active`
- [[modules/texts]] — `gamer_pickup_ineligible`, `gamer_pickup_no_accounts`, `gamer_pickup_success`
- [[modules/utils]] — `escape`, `clean_messages`, `add_message_history`
