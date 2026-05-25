# Module: sheet_synchonizer.py

**Type:** Data import  
**Lines:** 173  
**Class:** `GoogleSheetSynchonizer`

## Responsibilities

Reads the Accounts tab from Google Sheets and updates MongoDB. Never writes to the sheet. Never modifies account assignment (Option C — see [[DECISIONS]]).

After completing all account updates, calls `ProgressMonitor.check_all()`.

## Column Layout (Accounts tab, 0-indexed)

| Index | Field | Notes |
|---|---|---|
| 0 | Profile (Octo name) | Primary key for upsert |
| 1 | Login | |
| 2 | Password | |
| 3 | Proxy | Skip if `#N/A` |
| 4 | Old Gamer | Season 1 owner — ignored |
| 5 | Active | Skip if `#N/A` |
| 6 | Gamer | Season 3 assignment — **ignored per Option C** |
| 7 | TP Start | `points;rank;floor` format — Season 3 baseline |
| 8+ | Daily columns | `points;rank;floor` per sync day — rightmost = latest |

## Sync Logic (`grab_accounts()`)

**Skip conditions:** profile empty, row < 6 columns, Active == `#N/A`, Proxy == `#N/A`.

**For new accounts** (not in DB):
- Insert with seed `progress_history` entry from TP Start (col 7): `{synced_at: now, tower_points: tp_start.points, delta: tp_start.points, gamer_id: null}`
- `status: "released"`, `gamer_id: null`

**For existing accounts:**
- Parse latest tower points from rightmost column (`account[-1]`)
- Compute `delta = new_tower_points - progress_history[-1].tower_points`
- Append new `progress_history` entry (delta may be 0 or negative — appended regardless)
- Update `last_synced_at`; update `last_progress_at` only if delta > 0

**Gamer column:** Read but ignored. `gamer_id` is never written by this module.

## Tower Point Parsing (`__parse_tower`)

Format: `points;rank;floor` (3 semicolon-separated values).

Handles: `NaN;NaN;NaN`, empty string, float row values, index out of range. Returns `{points: 0, rank: 0, floor: 0}` on any parse failure.

## Dependencies

- [[modules/mongodb]] — `put_account()`, `push_progress_entry()`
- [[modules/google_api]] — `get_accounts()` (returns raw sheet rows)
- [[modules/progress_monitor]] — `check_all()` called after sync completes

## Flows

- [[flows/sheet-sync]] — this module is the core of that flow
