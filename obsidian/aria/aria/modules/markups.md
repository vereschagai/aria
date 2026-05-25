# Module: markups.py

**Type:** Keyboard layouts  
**Lines:** 39

## Responsibilities

Pre-built `ReplyKeyboardMarkup` objects — one per role/screen. Referenced in [[modules/main]] when sending role home screens.

## Markup Objects

| Name | Used for |
|---|---|
| `superadmin_start` | Superadmin home screen |
| `admin_start` | Admin home screen |
| `start` | Gamer home screen |
| `operator_start` | Operator home screen |
| `support_start` | Support home screen |
| `confirm` | Confirm/cancel two-button keyboard |
| `back` | Single back button |
| `backaddressadd` | Back during address add flow |
| `backaddresschange` | Back during address change flow |

## Dependencies

Uses [[modules/buttons]] label constants. Used by [[modules/main]].
