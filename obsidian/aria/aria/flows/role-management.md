# Flow: Role Management

**Roles:** superadmin → admin → operator → support → gamer  
**Who manages what:** Superadmin manages admins. Admin (and superadmin) manages operators and support. Gamers join via referral.

## Add Role

All three add flows (admin, operator, support) share the same handlers.

```
1. Actor presses Add [Admin | Operator | Support] button
        ↓
2. admin_add() → detect which add is needed by message text
   Set FSM state: superadmin_add_admin / admin_add_operator / admin_add_support
   Send prompt text + markups.back
        ↓
3a. User shares a Telegram CONTACT:
    admin_added() fires

    if contact.user_id is None (no linked Telegram account):
      send texts.admin_add_wrong, stay in state

    Check if already in target role:
      is_admin(contact.user_id) / is_operator / is_support

    If already in role:
      Return to home (superadmin_start or admin_start depending on actor)
      send texts.admin_add_exists.format(contragent, name)

    If new:
      db.add_admin / add_operator / add_support (contact)
      Return to home
      send texts.admin_added.format(contragent, name)

3b. User sends non-contact message:
    admin_added_error() → send error text, stay in state
```

**No notification is sent to the newly added person.** They must press /start themselves to see their new role.

**No cross-role deduplication** — a user can be in multiple role collections simultaneously. Resolution order in `start()` determines what they see.

## Remove Role (Operator or Support)

```
1. Actor presses Remove [Operator | Support] button
        ↓
2. admin_remove() → fetch list from DB
   If empty → send empty-list text, return (no state change)
   If has users → build InlineKeyboardMarkup (label = username + phone, callback = user_id str)
                  TelegramState.admin_remove_operator / support_remove.set()
                  send list + back button
        ↓
3. Actor taps a user from the list (admin_remove_confirm() callback):
   If callback_data == "back":
     db.is_superadmin(from_user.id) → determine home state, return

   db.get_operator / get_support_user ({id: int(data)}) → fetch entity
   If found:
     Set confirm state (admin_remove_operator_confirm / support_remove_confirm)
     state.set_data({"id": entity_id})
     send confirm text with markups.confirm (confirm/cancel keyboard)
   If not found:
     send admin_remove_confirm_error
        ↓
4a. Actor taps "Подтвердить" (admin_remove_confirmed()):
    state.get_data() → search dict
    db.get_operator / get_support_user (search) → get entity with id field
    Return to appropriate home state
    db.remove_operator / remove_support (search)
    dp.current_state(chat=entity["id"], user=entity["id"]).finish()
      ← wipes removed user's FSM state (effectively logs them out)
    send texts.admin_removed.format(contragent, username)

4b. Actor taps "Отмена":
    start() handler fires → role resolution → home state
```

## Remove Admin (Superadmin only)

Same as remove-operator flow but using `superadmin_remove_admin` / `superadmin_remove_admin_confirm` states and `db.get_admins()` / `db.remove_admin()`.

## Gamer Signup (Referral)

See [[flows/start-role-resolution]] for the full referral parsing logic inside `start()`.

Summary: new user sends `/start <user_id>` → referral validated → `db.add_gamer()` → directed to add wallet address → [[flows/wallet-management]].

## End States

- Add: actor returns to role home. New user must press /start to activate role.
- Remove: actor returns to role home. Removed user's FSM state is wiped; their next `/start` will route them to gamer/newcomer.

## Modules

- [[modules/main]] — `admin_add`, `admin_added`, `admin_added_error`, `admin_remove`, `admin_remove_confirm`, `admin_remove_confirmed`
- [[modules/mongodb]] — `is_admin/operator/support`, `add_admin/operator/support`, `remove_admin/operator/support`, `get_admins/operators/support_users`, `count_admins/operators/support_users`
- [[modules/texts]] — add/remove string variants per contragent
- [[modules/state]] — `superadmin_add_admin`, `admin_add_operator`, `admin_add_support`, `admin_remove_operator`, `admin_remove_operator_confirm`, `support_remove`, `support_remove_confirm`, `superadmin_remove_admin`, `superadmin_remove_admin_confirm`
- [[modules/markups]] — `back`, `confirm`, role home screens
