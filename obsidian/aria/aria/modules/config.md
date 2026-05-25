# Module: config.py

**Type:** Configuration seed  
**Lines:** 10

## Responsibilities

Defines in-memory default values for the `config` MongoDB collection. Seeded to the DB on startup via `init()` in [[modules/main]] only if the config document doesn't already exist. The live DB value governs once set.

## Configuration Fields

| Field | Default | Notes |
|---|---|---|
| `min_progress_points` | 50 | Minimum delta per sync for a gamer's account to pass the eligibility check. Fixed from 10 → 50 in code review. |
| `max_accounts_per_gamer` | 10 | Slot limit for concurrent active accounts |
| `inactivity_escalation_days` | 3 | Calendar days before escalation to support |
| `leaderboard_gap` | 4 | Rows above/below requesting gamer shown in leaderboard |
| `leaderboard_cooldown_days` | 7 | Reserved/unused |
| `inactivity_day_buffer_hours` | 6 | **Dead field** — kept for DB backwards compat. Has no effect on logic since calendar-day calculation was adopted. See [[DECISIONS]] (Calendar-day inactivity tracking). |

## Dependencies

None. Used by [[modules/mongodb]] `get_config()` and by [[modules/main]] `init()`.
