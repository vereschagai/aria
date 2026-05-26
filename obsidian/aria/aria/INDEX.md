# Aria — Knowledge Graph Index

## Architecture Docs
## Claude Memory (Hot Cache)
- [[memory/MEMORY]] — Boot index: protocol, quick rules, session handoff
- [[memory/project_aria]] — Project context: stack, season state, gaps, deployment
- [[memory/feedback_aria_workflow]] — Coding rules Claude must follow every session
- [[memory/reference_aria_codebase]] — Where things live: files, env vars, DB collections

> Read `aria/memory/MEMORY.md` via Obsidian MCP at the start of every session.

- [[CONTEXT]] — stack, architecture, components, dependencies
- [[DECISIONS]] — all architectural decision records (12 ADRs)
- [[PROGRESS]] — what is implemented
- [[REVIEW]] — design chat requests vs. implementation (gap analysis)
- [[NEXT]] — work queue

## Modules
- [[modules/main]] — entry point, dispatcher, all handlers (924 lines)
- [[modules/mongodb]] — database layer (all queries, 443 lines)
- [[modules/sheet_synchonizer]] — Google Sheets import
- [[modules/progress_monitor]] — inactivity tracking and escalation
- [[modules/operator_controller]] — operator/support routing and leaderboard
- [[modules/google_api]] — Google Sheets API wrapper
- [[modules/config]] — configuration defaults
- [[modules/state]] — FSM states (all 25 states)
- [[modules/utils]] — shared utilities
- [[modules/buttons]] — button label constants
- [[modules/texts]] — message string templates
- [[modules/markups]] — ReplyKeyboardMarkup objects

## User Flows

### System Flows
- [[flows/start-role-resolution]] — /start: role detection and routing (any user)
- [[flows/sheet-sync]] — sync cycle: Sheets → DB → inactivity check (superadmin trigger)

### Superadmin Flows
- [[flows/superadmin-config]] — view and edit configuration values
- [[flows/superadmin-broadcast]] — compose and send broadcast to all gamers

### Admin / Role Management
- [[flows/role-management]] — add/remove admin, operator, support; gamer signup via referral

### Gamer Flows
- [[flows/gamer-account-screen]] — account home screen (credentials, points, wallet)
- [[flows/wallet-management]] — add or change EVM wallet address
- [[flows/gamer-pickup]] — self-service account pickup (Season 4, auto-assignment)
- [[flows/on-demand-release]] — voluntary account release → support approval
- [[flows/proof-submission]] — submit proof for escalated account (catch-all message handler)
- [[flows/leaderboard]] — season points leaderboard (all roles)

### Inactivity / Escalation (System + Support)
- [[flows/inactivity-escalation]] — post-sync inactivity warning and escalation flow

## FSM State Map

```
None → superadmin_start → superadmin_configuration → superadmin_edit_configuration → superadmin_start
                        → superadmin_feed → superadmin_start
                        → superadmin_add_admin → superadmin_start
                        → superadmin_remove_admin → superadmin_remove_admin_confirm → superadmin_start

None → admin_start → admin_add_operator → admin_start / superadmin_start
                   → admin_add_support  → admin_start / superadmin_start
                   → admin_remove_operator → admin_remove_operator_confirm → admin_start
                   → support_remove → support_remove_confirm → admin_start / superadmin_start

None → operator_start → leaderboard → operator_start
None → support_start  → leaderboard → support_start

None → start → referral → start
             → account  → address       → account
                        → change_address → account
             → gamer_release_account → start
             → leaderboard → start
```
