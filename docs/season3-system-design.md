# Season 3 — System Design

This document records the design decisions made for Season 3 and how they evolved into the current implementation. It is the canonical reference for *why* things work the way they do. For *what* is implemented, see [CLAUDE.md](../CLAUDE.md), [docs/data-model.md](data-model.md), and [docs/flows.md](flows.md).

---

## Design decisions

| # | Decision | Status |
|---|---|---|
| 1 | Good progress = +50 tower points per sync (configurable `min_progress_points`) | ✅ Implemented as designed |
| 2 | All strictly `active` accounts must show good progress before gamer qualifies for a new one | ✅ Implemented — `escalated` and `pending_release` accounts are excluded from this check |
| 3 | Inactivity measured in calendar days (UTC) | ✅ Implemented — original design proposed an 18h buffer; changed to clean calendar days |
| 4 | Sync stays manual; future automation via Octo+Puppeteer is a separate project | ✅ Manual sync in place |
| 5 | Season 3 already started — no start button needed. Starting points snapshotted via one-time migration script | ✅ `migration_season3.py` run once on production |
| 6 | Full ownership chain tracked (array of all past owners with timestamps) | ✅ `ownership_history` array on each account |
| 7 | Maximum accounts per gamer enforced (configurable `max_accounts_per_gamer`, default 10) | ✅ Checked in `check_assignment_eligibility` |
| 8 | Assignment is DB-only (Option C) — Google Sheet gamer column is ignored by synchonizer | ✅ Synchonizer never touches `gamer_id` or `ownership_history` |
| 9 | Gamer keeps points earned on an account even after releasing it | ✅ Season 3 score = Σ positive deltas where `progress_history[].gamer_id == gamer._id` across all accounts |
| 10 | On-demand release by gamer, requires support approval | ✅ `pending_release` status + support inline keyboard |

---

## Functional requirements vs implementation

### R1 — Sheet synchronizer

**Original requirement:**
- Resolve `gamer` username → `gamers._id` on each sync, store `gamer_id`
- Append progress_history entry with delta and current gamer_id
- Update `last_progress_at` if delta ≥ `min_progress_points`

**What changed:**
The ownership-from-sheet approach was replaced with Option C. The synchonizer **never resolves or writes `gamer_id`**. Assignment happens exclusively via direct DB operations by operators. The synchonizer only reads the sheet for game data (login, password, proxy, tower points) and appends progress history entries using whatever `gamer_id` is already on the account in the DB.

**Current implementation** (`sheet_synchonizer.py`):
- Skip row if `col[5] == "#N/A"` (not active in S3) or `col[3] == "#N/A"` (no proxy)
- New accounts: inserted with `gamer_id = null`, `season3_start_points` from col 7
- Existing accounts: `$set` only `profile, login, password, proxy, tower, last_synced_at`; `$push` a progress entry; never touch ownership

---

### R2 — Gamer Season 3 score

**Original requirement:**
Points = Σ of `progress_history` entries where `entry.gamer_id == gamer._id`, delta > 0, across ALL accounts.

**What changed:** Nothing — implemented exactly as designed.

**Current implementation** (`mongodb.py::get_gamer_season_points`, `get_all_gamers_season_points`):
```python
pipeline = [
    { "$unwind": "$progress_history" },
    { "$match": { "progress_history.gamer_id": gamer_oid, "progress_history.delta": { "$gt": 0 } } },
    { "$group": { "_id": None, "total": { "$sum": "$progress_history.delta" } } }
]
```
The leaderboard uses `get_all_gamers_season_points()` — a single aggregation that groups by `gamer_id` across all accounts.

---

### R3 — Assignment eligibility

**Original requirement:**
1. All assigned accounts have `delta >= min_progress_points` on last progress entry
2. No assigned account has `status == "escalated"`
3. Count < `max_accounts_per_gamer`

**What changed:**
- Condition 2 was revised: escalated and `pending_release` accounts count toward the slot limit but are **not** subject to the progress check (it would be unfair to block a gamer from requesting a new account because an escalated account can no longer make progress).
- A fourth condition was added: gamer cannot have ≥ 5 previously-owned accounts sitting in the available pool (`available_for_pickup: true`). This prevents pool congestion.

**Current implementation** (`mongodb.py::check_assignment_eligibility`):
```python
# 1. Slot limit
occupied = find({ gamer_id, status: { $in: ["active","escalated","pending_release"] } })
if len(occupied) >= max_accounts_per_gamer:
    return False, "Достигнут лимит аккаунтов"

# 2. Progress check — strictly active accounts only
for account in occupied:
    if account["status"] != "active": continue
    if not history or history[-1]["delta"] < min_progress_points:
        return False, f"Аккаунт {profile} — недостаточно прогресса"

# 3. Pool congestion cap
if count_gamer_available_releases(gamer_oid) >= 5:
    return False, "У вас 5+ аккаунтов ожидают переназначения"
```

---

### R4 — Inactivity monitoring

**Original requirement:**
```
days_inactive = floor((now - last_progress_at).hours / 18)
```
- days_inactive == 1 → first warning
- days_inactive == 2 → second warning
- days_inactive >= 3 → escalate

**What changed:**
The 18-hour formula was replaced with **calendar days (UTC)**. The formula `floor(hours / 18)` overcounts: June 1 → June 3 gives 2 calendar days but the formula could return 3 if the times align. Clean calendar-day arithmetic is simpler and predictable.

The multi-step warning (1 warning, 2 warnings) was simplified: any day with `days_inactive >= 1` and `< escalation_threshold` sends a single warning. The deduplication (one notification per calendar day) is handled by `last_notified_day` ordinal comparison.

**Current implementation** (`progress_monitor.py::check_all`):
```python
days_inactive = (datetime.utcnow().date() - baseline.date()).days

if days_inactive >= escalation_days and status != "escalated":
    await self._escalate(account)
elif days_inactive >= 1 and status != "escalated":
    await self._warn_gamer(account, days_inactive)
    # set last_notified_day = today.toordinal()
```

---

### R5 — Support role

**Original requirement:**
- New role between admin and gamer
- Receives escalation messages with inline keyboard
- Decides: progress possible → release to pool; no progress → mark inactive

**What changed:** Nothing significant. Implemented as designed. Added `pending_release` as a fifth account status (on-demand release, see R6).

**Current implementation:**
- `support` MongoDB collection, managed via admin (same contact-share flow as operators)
- Support users receive both inactivity escalations (`progress_monitor._escalate`) and on-demand release requests (`gamer_release_account_select` in `main.py`)
- Inline buttons use account `_id` hex in `callback_data` (not profile name — Telegram's 64-byte limit)

---

### R6 — On-demand account release (added post-design)

**Not in original design.** Added to resolve the situation where a gamer cannot make progress on an account but is below the inactivity escalation threshold, blocking them from requesting a new account.

**Design:**
- Gamer taps 🔓 Освободить аккаунт → selects from their active accounts
- Account transitions to `pending_release` (gamer_id stays set)
- Support receives inline decision: approve (→ `released`) or deny (→ back to `active`)
- `pending_release` accounts are excluded from the progress check in eligibility but counted toward the slot limit

---

## Account status lifecycle

```
                  ┌── 1+ inactive days ──▶  escalated
                  │                              │
  [unassigned] ──▶ active                        ├── support: progress possible ──▶ released
                  │                              │
                  │                              └── support: no progress ──────▶ inactive
                  │
                  └── gamer: release request ──▶ pending_release
                                                      │
                                                      ├── support: approve ──▶ released
                                                      └── support: deny   ──▶ active
```

| Status | `available_for_pickup` | Counted in slot limit | Progress-checked |
|---|---|---|---|
| `active` | false | ✅ | ✅ |
| `escalated` | false | ✅ | ❌ |
| `pending_release` | false | ✅ | ❌ |
| `released` | **true** | ❌ | ❌ |
| `inactive` | false | ❌ | ❌ |

---

## One-time migration

`migration_season3.py` — run once on production before the Season 3 bot was deployed.

Seeds each existing account with:
- `gamer_id` resolved from current `gamer` username string
- `season3_start_points` from current `tower.points`
- `ownership_history` with one open entry for current owner
- `progress_history = []`
- `status = "active"`, `available_for_pickup = false`
- `last_progress_at = null`, `last_synced_at = null`, `last_notified_day = null`
- `escalated_at = null`, `pending_proof = null`, `release_request = null`

Also adds Season 3 config fields to the `config` collection if missing.

---

## MongoDB indexes added for Season 3

```python
await db.support.create_index("id", unique=True)
await db.accounts.create_index("gamer_id")
await db.accounts.create_index("status")
await db.accounts.create_index("available_for_pickup")
await db.accounts.create_index("last_progress_at")
await db.accounts.create_index([("progress_history.gamer_id", ASCENDING)])
```
