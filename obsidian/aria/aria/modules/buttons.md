# Module: buttons.py

**Type:** UI constants  
**Lines:** 34

## Responsibilities

Module-level string constants for all Telegram button labels (Russian). Used as `Text(equals=buttons.X)` filter arguments in [[modules/main]] handler registrations.

All button text is in Russian. Examples: pickup button, release button, leaderboard button, confirm/back/cancel.

## Dependencies

Used by [[modules/main]], [[modules/operator_controller]], [[modules/markups]].

## Related

- [[modules/texts]] — full message string templates
- [[modules/markups]] — keyboard layouts that use these labels
