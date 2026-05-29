# Aria Docs Index

All project documentation for the Aria Telegram bot. Migrated from `docs/` in the codebase on 2026-05-28.

---

## Core references

| Document | Description |
|---|---|
| [[architecture]] | System overview, technology choices, key design decisions, sequence diagrams for sync/leaderboard/onboarding/deploy flows |
| [[data-model]] | Full MongoDB schema for all collections (`admin`, `operators`, `support`, `gamers`, `accounts`, `config`, `messages`), field reference, status lifecycle, all `MongoDb` method signatures |
| [[flows]] | Every user-facing conversation flow — role resolution, superadmin/admin/operator/support/gamer flows, inactivity escalation, sheet sync |

## How-to guides

| Document | Description |
|---|---|
| [[adding-features]] | Step-by-step guide to implementing a new feature: FSM states, buttons, markups, texts, MongoDB methods, handler registration, multi-role handlers, back/cancel wiring |

## Season design records

| Document | Description |
|---|---|
| [[season3-system-design]] | Design decisions for Season 3 — original requirements vs what was implemented, inactivity monitoring rationale, ownership model (Option C), migration notes |
| [[season4-system-design]] | ADR for Season 4 instant auto-assign — removes operator bottleneck, pickup priority algorithm, `season_picked_up` flag, migration steps, removed code |

## Implementation plans

| Document | Description |
|---|---|
| [[plans/2026-05-27-sprint-d-support-dashboard]] | Sprint D plan — support task dashboard with pagination, DM buttons on escalation/release notifications. Status: ✅ Implemented |

---

## Quick links

- [[data-model#accounts|Account status lifecycle]]
- [[data-model#MongoDb method index|MongoDb method index]]
- [[flows#Gamer flows|Gamer flows]]
- [[flows#Inactivity escalation flow|Inactivity escalation flow]]
- [[season4-system-design#Pickup priority|Season 4 pickup priority]]
