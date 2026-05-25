# Module: progress_monitor.py

**Type:** Inactivity monitor  
**Lines:** 172  
**Class:** `ProgressMonitor`

## Responsibilities

Called after every sync by [[modules/sheet_synchonizer]]. Checks all active assigned accounts for inactivity and either warns the gamer or escalates to support.

## Inactivity Calculation

```python
days_inactive = (datetime.utcnow().date() - baseline.date()).days
```

`baseline` = `last_progress_at` if set, else `ownership_history[-1].assigned_at`.

Calendar-day difference only — no hour-based formula. See [[DECISIONS]] (Calendar-day inactivity tracking).

Deduplication: `last_notified_day` ordinal on the account prevents re-sending on same calendar day.

## Decision Tree (`check_all()`)

```
For each active assigned account:
  └── days_inactive >= escalation_days AND status != "escalated"
        → _escalate()
  └── elif days_inactive >= 1 AND status != "escalated"
        → _warn_gamer()
  (Accounts with status "escalated" or "pending_release" are skipped)
```

## `_warn_gamer(account, days_inactive)`

- Sends MarkdownV2 warning text to gamer's Telegram ID (from [[modules/texts]])
- Updates `last_notified_day` on account
- If gamer has no Telegram ID: skip (checked via `gamer.get("id")`)

## `_escalate(account)`

1. Sets `status = "escalated"`, `escalated_at = now`, `last_notified_day = today_ordinal`
2. Fetches last 5 `progress_history` entries and formats them
3. Sends escalation card to **all support users** with inline keyboard:
   - `support_progress` — "progress is possible"
   - `support_noprogress` — "no progress possible"
4. Forwards `pending_proof` message if present
5. Sends gamer a notification that their account was escalated

## Support Decision Resolution

Handled in [[modules/main]] `support_decision()` callback:
- `support_progress` → `release_account(status="released")` — account back to pool
- `support_noprogress` → `set_account_status(status="inactive")` — account marked inactive

Points already in `progress_history` are preserved regardless of decision.

## Dependencies

- [[modules/mongodb]] — `get_active_assigned_accounts()`, `get_gamer()`, `get_support_users()`, `set_account_status()`, `release_account()`
- [[modules/texts]] — `gamer_inactivity_warning`, `gamer_escalated`, `support_escalation`
- aiogram Bot — `bot.send_message()`

## Flows

- [[flows/inactivity-escalation]] — this module implements that entire flow
