config = {
    "leaderboard_gap": 4,
    "leaderboard_cooldown_days": 7,

    # Season 3
    "min_progress_points": 50,        # tower points delta per day to count as good progress
    "max_accounts_per_gamer": 10,     # maximum simultaneous active accounts per gamer
    "inactivity_escalation_days": 3,  # days of no progress before support escalation
    "inactivity_day_buffer_hours": 6, # dead field — kept for DB backwards compat; not read at runtime
}
