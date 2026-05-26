# Module: texts.py

**Type:** Message string templates  
**Lines:** 331

## Responsibilities

All bot-facing message strings in Russian, pre-escaped for MarkdownV2 where needed. Used throughout [[modules/main]], [[modules/progress_monitor]], [[modules/operator_controller]].

## String Groups

| Group | Key strings |
|---|---|
| Superadmin | `superadmin_start`, `superadmin_configuration`, `superadmin_edit_configuration`, `superadmin_config_updated`, `superadmin_config_value_wrong`, `superadmin_feed`, add/remove admin flow |
| Admin | `admin_start`, add/remove operator and support strings |
| Gamer general | `gamer_start`, `gamer_referral_link`, `gamer_address`, `gamer_account`, `gamer_no_leaderboard` |
| Season pickup | `gamer_pickup_ineligible`, `gamer_pickup_no_accounts`, `gamer_pickup_success` |
| Inactivity | `gamer_inactivity_warning`, `gamer_escalated`, `gamer_account_released`, `gamer_account_inactive`, `gamer_proof_received` |
| Release flow | `gamer_release_account_prompt`, `gamer_release_account_no_accounts`, `gamer_release_account_sent`, `gamer_release_account_approved`, `gamer_release_account_denied`, `support_release_request`, `support_release_decision_done` |
| Support | `support_start_text`, `support_escalation`, `support_decision_done` |
| Operator | `operator_start` — moved here from hardcoded string in `operator_controller.py` (fixed in code review) |
| Misc | `internal_error` |

## Known Issues

- `gamer_account` template (line 184) contains hardcoded `@goldalfsupp` support handle — not configurable via DB.

## Dependencies

Used by [[modules/main]], [[modules/progress_monitor]]. (operator_controller removed Sprint A)
