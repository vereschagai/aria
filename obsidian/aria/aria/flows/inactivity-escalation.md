# Flow: Inactivity Escalation

**Trigger:** Automatic — called at end of every [[flows/sheet-sync]] via `progress_monitor.check_all()`  
**Actor:** System  
**Handler:** `ProgressMonitor.check_all()`, `_warn_gamer()`, `_escalate()`, then `support_decision()` in main.py (line 860)

## Part 1 — Post-Sync Check

```
After every sheet sync:
        ↓
progress_monitor.check_all()
  db.get_config() → read inactivity_escalation_days (default 3)
  db.get_active_assigned_accounts()
    → all accounts where gamer_id != null AND status == "active"
        ↓
  For each account:
    baseline = last_progress_at  (or ownership_history[-1].assigned_at if no progress yet)
    if no baseline → skip

    days_inactive = (today_utc.date() - baseline.date()).days

    if days_inactive < 1 → skip
    if last_notified_day == today_ordinal → skip (already acted today)
        ↓
    if days_inactive >= escalation_days AND status != "escalated":
      → _escalate(account)

    elif days_inactive >= 1 AND status != "escalated":
      → _warn_gamer(account, days_inactive)
         db.set_account_status(profile, status, {"last_notified_day": today_ordinal})
```

## Part 2 — Warn Gamer (Day 1–2)

```
_warn_gamer(account, days_inactive):
  db.get_gamer_by_id(gamer_id)
  if not found or no "id" field → return

  send texts.gamer_inactivity_warning.format(profile, days) to gamer
```

## Part 3 — Escalate (Day 3+)

```
_escalate(account):
  db.get_gamer_by_id(gamer_id)

  db.set_account_status(profile, "escalated", {
    "escalated_at": now,
    "last_notified_day": now.toordinal()
  })

  Build last-5 progress_history summary (formatted dates and deltas)

  db.get_support_users()
  Build InlineKeyboardMarkup:
    [✅ Прогресс возможен | callback: support_progress:<oid>]
    [❌ Нет прогресса     | callback: support_noprogress:<oid>]

  For each support user:
    send texts.support_escalation + inline keyboard (MarkdownV2)
    if account.pending_proof: bot.forward_message(proof)
    errors caught per-user (try/except, logged, continue)

  if gamer has Telegram id:
    send texts.gamer_escalated.format(profile) to gamer
```

## Part 4 — Support Decision

```
Support taps ✅ "Прогресс возможен":
  db.is_support(from_user.id) → verify role
  db.get_account_by_object_id(oid) → verify status == "escalated"
  db.release_account(profile, "released", released_at=now)
    → closes ownership_history entry, clears gamer_id, $unsets pending_proof + release_request
  send texts.gamer_account_released to gamer
  send texts.support_decision_done to support user

Support taps ❌ "Нет прогресса":
  same verification
  db.release_account(profile, "inactive", released_at=now)
  send texts.gamer_account_inactive to gamer
  send texts.support_decision_done to support user
```

Points already in `progress_history` are preserved in both outcomes.

## Proof Submission (separate flow, affects escalation)

See [[flows/proof-submission]]. When `_escalate()` runs on an account that has `pending_proof`, the proof is forwarded to support users alongside the escalation card.

## End State

- Account: `escalated` → `released` (back to pool) or `inactive`
- Gamer notified of outcome
- Second support user clicking a resolved escalation card gets "Аккаунт уже обработан"

## Key Design Decisions

- Calendar-day diff only — not hours (see [[DECISIONS]])
- `pending_release` accounts excluded from check entirely
- Escalated accounts exempt from eligibility block — gamers can still pick new accounts (see [[DECISIONS]])
- `last_notified_day` ordinal prevents re-notifying on the same calendar day
- If `get_support_users()` returns empty, account is still marked escalated (no notifications sent)

## Modules

- [[modules/progress_monitor]] — `check_all`, `_warn_gamer`, `_escalate`
- [[modules/main]] — `support_decision()` callback
- [[modules/mongodb]] — `get_active_assigned_accounts`, `get_gamer_by_id`, `get_support_users`, `set_account_status`, `release_account`, `get_account_by_object_id`
- [[modules/texts]] — `gamer_inactivity_warning`, `gamer_escalated`, `support_escalation`, `support_decision_done`, `gamer_account_released`, `gamer_account_inactive`
