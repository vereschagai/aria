# Module: operator_controller.py

**Type:** Operator/support routing  
**Lines:** 110  
**Class:** `OperatorController`

## Responsibilities

- Role resolution for operator and support users on `/start`
- Leaderboard fetch and render
- Handler registration via `init_handlers()`

## Role Resolution (`main(user_id)`)

Resolves role order: superadmin → admin → operator → support → gamer → newcomer.

Called from [[modules/main]] `start()` when user is routed to operator scope.

## Leaderboard (`__leaderboard()`)

1. Calls `get_all_gamers_season_points()` — single aggregation, returns list sorted desc by season points
2. Batch-resolves ObjectIds → usernames in one `find({_id: {$in: oids}})` call
3. Renders MarkdownV2 string with `leaderboard_gap` rows above/below the requesting gamer
4. Handles gamer-not-on-board case via `StopIteration` catch

**Cost:** 2 DB round-trips regardless of guild size.

## Known Issues (fixed in code review)

- `is_new_year` parameter on `__print_leaderboard` was dead code — removed
- Hardcoded `"Че нада?"` string moved to [[modules/texts]] as `operator_start`

## Dependencies

- [[modules/mongodb]] — `get_all_gamers_season_points()`, `get_gamer_by_id()`
- [[modules/texts]] — `operator_start`, leaderboard string building
- [[modules/state]] — `TelegramState.leaderboard`

## Flows

- [[flows/leaderboard]] — this module implements leaderboard rendering
