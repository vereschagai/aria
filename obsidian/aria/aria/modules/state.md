# Module: state.py

**Type:** FSM state definitions  
**Lines:** 31  
**Class:** `TelegramState(StatesGroup)`

## All States

### Superadmin
- `superadmin_start`
- `superadmin_add_admin`
- `superadmin_remove_admin`
- `superadmin_remove_admin_confirm`
- `superadmin_configuration`
- `superadmin_edit_configuration`
- `superadmin_feed`

### Admin
- `admin_start`
- `admin_add_operator`
- `admin_remove_operator`
- `admin_remove_operator_confirm`
- `admin_add_support`

### Gamer
- `start`
- `referral`
- `account`
- `address`
- `change_address`
- `gamer_release_account`

### Operator / Support
- `operator_start`
- `leaderboard`
- `support_start`
- `support_remove`
- `support_remove_confirm`

## Dependencies

Used by [[modules/main]] (all handler registrations and state transitions). operator_controller removed in Sprint A — leaderboard state now lives in main.
