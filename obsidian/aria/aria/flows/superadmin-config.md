# Flow: Superadmin Configuration

**Trigger:** "⚙️ Конфигурация" button in `TelegramState.superadmin_start`  
**Actor:** Superadmin  
**Handlers:** `superadmin_configuration()` (line 190), `superadmin_edit_configuration()` (line 204), `superadmin_edit_value_configuration()` (line 227)

## View Config

```
1. Superadmin presses "⚙️ Конфигурация"
        ↓
2. superadmin_configuration()
   db.get_config() → fetch all config fields
   Build InlineKeyboardMarkup:
     one button per field: label = "field: value", callback_data = field_name
     + back button
   TelegramState.superadmin_configuration.set()
   Send texts.superadmin_configuration + inline keyboard
```

## Edit a Field

```
3. Superadmin taps a config field button
        ↓
4. superadmin_edit_configuration() callback fires
   If callback_data == "back":
     TelegramState.superadmin_start.set() → send superadmin home, return

   db.get_config() → re-fetch current value
   TelegramState.superadmin_edit_configuration.set()
   state.set_data({"field": field_name})
   callback_query.answer("")
   send texts.superadmin_edit_configuration.format(field, current_value)
     + ReplyKeyboardRemove() (clears keyboard while waiting for input)
        ↓
5. Superadmin types new value
        ↓
6. superadmin_edit_value_configuration() fires (TelegramState.superadmin_edit_configuration)
   state.get_data() → get field name

   Validation:
     field == "validation_live" → accept "true" or "false" (case-insensitive), cast to bool
     all other fields → accept digits only (message.text.isdigit()), cast to int

   INVALID → send texts.superadmin_config_value_wrong.format(field)
              stay in superadmin_edit_configuration, gamer can retry

   VALID → db.update_config(field, value)
           state.reset_data()
           TelegramState.superadmin_start.set()
           send texts.superadmin_config_updated.format(field, value) + markups.superadmin_start
```

## End State

`TelegramState.superadmin_start`. Config updated in DB.

## Config Fields

See [[modules/config]] for full list. Key editable fields: `min_progress_points`, `max_accounts_per_gamer`, `inactivity_escalation_days`, `leaderboard_gap`.

## Edge Cases

- `_id` field is skipped in the inline keyboard build loop
- Integer fields have no upper/lower bound validation — any digit string is accepted
- The only boolean-type field is `validation_live`; all others are integers
- New fields added to the config collection after the first seed will appear automatically on the config screen

## Modules

- [[modules/main]] — handlers
- [[modules/mongodb]] — `get_config`, `update_config`
- [[modules/config]] — default values reference
- [[modules/texts]] — `superadmin_configuration`, `superadmin_edit_configuration`, `superadmin_config_updated`, `superadmin_config_value_wrong`
- [[modules/state]] — `TelegramState.superadmin_configuration`, `TelegramState.superadmin_edit_configuration`
