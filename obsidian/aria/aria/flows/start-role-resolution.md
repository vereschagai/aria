# Flow: /start — Role Resolution

**Trigger:** `/start` command, OR back/cancel from any FSM state listed in the handler decorator  
**Actor:** Any Telegram user  
**Handler:** `start()` — main.py line 107

## Steps

```
1. User sends /start (or presses back from another state)
        ↓
2. Role resolution (sequential DB checks, first match wins):

   is_superadmin(user_id)?
     YES → TelegramState.superadmin_start.set()
           send texts.superadmin_start + markups.superadmin_start
           STOP

   is_admin(user_id)?
     YES → TelegramState.admin_start.set()
           if username changed: db.update_gamer({"id": uid}, {"username": new_username})
           send texts.admin_start + markups.admin_start
           STOP

   is_operator(user_id)?
     YES → operator_controller.main(user_id)
           (re-runs full role chain using bot.send_message)
           STOP

   is_support(user_id)?
     YES → TelegramState.support_start.set()
           send texts.support_start_text + markups.support_start
           STOP

   Gamer/newcomer path:
     Look up by id → if found: available = True
     Else look up by username → if found: update gamer.id, available = True
     Else: parse /start payload for referral integer
           validate referral (not self, must be existing gamer/admin/etc.)
           available = (valid referral found)
        ↓
3. If not available:
   send texts.gamer_only_invite_access
   STOP (no state set)

   If available but no Telegram username:
   send texts.gamer_no_username
   STOP (no state set)

   If newcomer with valid referral:
   db.add_gamer(id, username, referral)  ← creates gamer doc

   TelegramState.start.set()
   send texts.gamer_start + markups.start
   clean_messages, add_message_history
```

## End State

Appropriate role home screen FSM state (`superadmin_start`, `admin_start`, `operator_start`, `support_start`, or `start`). No state if user has no access.

## States That Route Here (back navigation)

`referral`, `account`, `address`, `change_address`, `leaderboard`, `superadmin_remove_admin_confirm`, `admin_remove_operator_confirm`, `support_remove_confirm`, `superadmin_feed`, `superadmin_add_admin`, `admin_add_operator`, `admin_add_support`, `gamer_release_account`

## Edge Cases

- User without Telegram username can't complete signup — must add a username first.
- No notification is sent to the newly created gamer's referrer.
- Roles are not mutually exclusive at DB level — a user could theoretically be in multiple collections. Resolution order (superadmin first) determines what they see.
- `skip_updates=False` at polling start means messages during downtime are replayed on restart.

## Modules

- [[modules/main]] — handler
- [[modules/mongodb]] — `is_superadmin`, `is_admin`, `is_operator`, `is_support`, `is_gamer`, `add_gamer`, `update_gamer`
- [[modules/operator_controller]] — `main()` for operators
- [[modules/texts]], [[modules/markups]], [[modules/state]]
