# Aria — Architecture Decision Records

---

## Option C: DB-only gamer assignment (no sheet writes)

**Status:** Accepted

**Context:** Google Sheet has a "Gamer" column (col 6) that historically determined account ownership. The synchonizer was overwriting DB assignment on every sync, making bot-managed ownership impossible.

**Decision:** The sheet is a data import source only. `gamer_id` and ownership fields are never written by `GoogleSheetSynchonizer`. Assignment happens exclusively through bot actions (`pickup_account()`, `release_account()`). The sheet's gamer column is read during Season 3 migration only, then permanently ignored.

**Consequences:** Sheet gamer column goes stale. Operators no longer manage assignment via spreadsheet — all assignment flows through the bot. The synchonizer's `update_fields` dict is explicit and never includes `gamer_id`, `gamer`, or `ownership_history`.

---

## Season 3 scoring: cumulative positive progress_history deltas

**Status:** Accepted

**Context:** Season 1 scoring used raw `tower.points` (absolute height). Season 3 target is tower points earned during the season, across all accounts a gamer has ever owned.

**Decision:** A gamer's season score = Σ `progress_history.delta` where `delta > 0` AND `progress_history.gamer_id == gamer._id`, across ALL accounts (current and past). Computed via a single MongoDB aggregation (`get_all_gamers_season_points()`). Negative deltas (game resets) are ignored. Points earned on a released account are kept permanently.

**Consequences:** Score is retroactive — points attributed to the gamer who owned the account at sync time, not current owner. One aggregation covers the entire leaderboard in one DB round-trip.

---

## Season 4: seed progress_history entry replaces season3_start_points

**Status:** Accepted

**Context:** Season 3 stored a `season3_start_points` field as the baseline for delta calculation. This created a special-case branch in the synchonizer (`prev_points = history[-1] if history else season3_start_points`). Also, starting points did not appear in gamer balances.

**Decision:** Remove `season3_start_points`. Instead, `migration_season4.py` prepends a seed entry to `progress_history`: `{synced_at: now, tower_points: start_points, delta: start_points, gamer_id: <previous_owner_oid>}`. Starting points are now attributed to the original owner and appear in their season balance. Synchonizer always uses `history[-1].tower_points` as baseline — no special case.

**Consequences:** Starting tower points count toward the original owner's season score. New accounts inserted by the synchonizer get a seed entry with `gamer_id: null` (uncredited until someone picks up the account).

---

## Season 4: remove available_for_pickup field

**Status:** Accepted

**Context:** `available_for_pickup: bool` was always redundant with `status == "released"`. Every query using it was equivalent to a status check.

**Decision:** Remove `available_for_pickup` from all accounts. Pickup eligibility is determined solely by `status == "released"`. The `pickup_account()` query filters on `status: "released"`.

**Consequences:** One fewer field and one fewer index. All code paths that previously checked `available_for_pickup` check `status` instead. Migration unsets the field.

---

## Season 4: instant auto-assign replaces operator-mediated request flow

**Status:** Accepted

**Context:** Season 3 account request flow: gamer taps "Запросить аккаунт" → all operators notified → operator updates sheet → superadmin syncs → account assigned. This created a bottleneck dependent on operator availability.

**Decision:** Replace with instant self-service: gamer taps "🎮 Взять аккаунт" → eligibility check → `pickup_account()` assigns atomically → gamer receives credentials immediately. No operator notification, no intermediate FSM state, no sheet update required.

**Consequences:** Operators are no longer involved in account assignment. Account selection is automatic (priority-ordered, not gamer-chosen). Race conditions handled by `findOneAndUpdate` with `status == "released"` guard.

---

## Season 4: pickup priority — own accounts first, then inactive-owner accounts

**Status:** Accepted

**Context:** With all accounts going into a shared pool on season reset, a prioritisation rule was needed to avoid gamers losing their established accounts to strangers.

**Decision:** Two-tier priority for `pickup_account()`:
- **Priority 1:** accounts where this gamer appears anywhere in `ownership_history.gamer_id`, sorted descending by `tower.points`.
- **Priority 2:** remaining released accounts whose last owner has `season_picked_up != true` (inactive this season) or has no prior owner, sorted descending by `tower.points`.
Accounts whose last owner is still active this season are excluded from Priority 2 — reserved for their Priority 1 pickup.

**Consequences:** Returning gamers reliably get their best previously-owned account back. Fresh accounts from inactive players are available to new gamers. Active gamers' released accounts are not poached by others.

---

## season_picked_up flag on gamers

**Status:** Accepted

**Context:** Priority 2 requires knowing whether a previous account owner "plays this season." Querying active account counts per owner at pickup time would require N+1 DB calls or a `$lookup` aggregation.

**Decision:** Add `season_picked_up: bool` (sparse, absent = falsy) to the `gamers` collection. Set to `true` on first `pickup_account()` call via `mark_gamer_season_active()` (idempotent). Priority 2 query checks `season_picked_up: true` on previous owner IDs — one batch `find()` instead of N lookups.

**Consequences:** Must be unset for all gamers in the next season migration (`migration_season5.py`). If never reset, all gamers remain "active" and Priority 2 pool shrinks to zero over time.

---

## Eligibility check: gamer_id ownership guard on progress_history

**Status:** Accepted

**Context:** Season 3 eligibility checked only `progress_history[-1].delta >= min_progress_points`. A gamer could pick up an account and immediately request another because the last sync delta belonged to the previous owner (who may have had good progress).

**Decision:** Add a second condition to the progress check: `progress_history[-1].gamer_id == this_gamer._id`. Both conditions must hold for each strictly `active` account. Escalated and `pending_release` accounts are exempt from this check (only their slot count matters).

**Consequences:** A gamer who just picked up an account is blocked from picking another until at least one sync runs under their ownership with `delta >= min_progress_points`. This is the intended "one pickup per sync cycle" gate without any date/time fields.

---

## Calendar-day inactivity (UTC) replaces 18-hour elapsed formula

**Status:** Accepted

**Context:** Original design used an 18-hour rolling window to determine "next day" (to handle 16:00 → 12:00 sync timing). This formula overcounted: June 1 12:00 → June 3 18:00 = 54h → 3 "days" by the formula, but only 2 calendar days elapsed.

**Decision:** Replace with `(datetime.utcnow().date() - baseline.date()).days`. Calendar days, UTC, no buffer. The `inactivity_day_buffer_hours` config field is now dead — kept in DB for backwards compat but not read at runtime.

**Consequences:** Inactivity counts are accurate regardless of sync timing. A gamer synced at 16:00 on day 1 and 10:00 on day 2 counts as 1 day inactive (correct). The dead config field should be cleaned up in a future migration.

---

## ObjectId hex in Telegram callback_data

**Status:** Accepted

**Context:** Telegram enforces a 64-byte hard limit on `callback_data`. Account profile names can exceed 50 characters, making `f"action:{profile}"` strings silently fail.

**Decision:** All `callback_data` strings use the account's MongoDB `_id` as a 24-character hex string. Handlers look up the account with `db.get_account_by_object_id(ObjectId(oid_str))`.

**Consequences:** No profile name length restriction. One extra DB lookup per callback. Pattern must be followed for any new callback handlers involving accounts.

---

## Support role: same management UX as operators

**Status:** Accepted

**Context:** Season 3 introduced a support role for handling inactivity escalations. The admin UI for adding/removing operators already existed.

**Decision:** Support users are managed identically to operators: admin adds via phone contact, admin removes via inline button selection. Stored in a separate `support` collection. Role resolved between operator and gamer in the hierarchy.

**Consequences:** Consistent UX across staff roles. Support is checked in `start()` and `OperatorController.main()` — both must be kept in sync if the role hierarchy changes.

---

## Gamer on-demand account release

**Status:** Accepted

**Context:** Without a release mechanism, gamers stuck on a dead account had to wait for 3-day escalation before they could request a new one — idle time with no ability to get productive work.

**Decision:** Gamer can tap "🔓 Освободить аккаунт" to voluntarily release an active account. Sets status to `pending_release`. Support receives a notification with "Разрешить освобождение" / "Отклонить" buttons. Approval → `release_account()` (account enters pool). Denial → status reverted to `active`, gamer notified. `pending_release` accounts count toward the slot limit but are exempt from the progress check.

**Consequences:** Gamers can exit dead accounts without waiting 3 days. Support remains the gatekeeper. The combination of `pending_release` slot counting + progress exemption enables the intended flow: release bad account → immediately request a new one.

---

## Leaderboard: batch ObjectId resolution

**Status:** Accepted

**Context:** Initial leaderboard implementation called `get_gamer_by_id()` once per entry in a loop (N+1 queries). For a guild of 50 gamers this fires 50 sequential DB calls on a user-facing tap.

**Decision:** `__leaderboard` in `OperatorController` resolves all gamer ObjectIds in one batch: `db.gamers.find({"_id": {"$in": oids}})`. Combined with the single `get_all_gamers_season_points()` aggregation, total leaderboard cost is 2 queries regardless of guild size.

**Consequences:** Leaderboard latency is O(1) in guild size. Direct `db.db.gamers` collection access used in the controller (same pattern as `mongo_scripts.py`).


## Sprint C: Community membership gate — all users blocked before role resolution

**Decision:** `/start` handler checks Telegram group membership (via `bot.get_chat_member`) before any role resolution (superadmin/support/gamer branches). Gate applies to ALL users including superadmins.
**Reason:** Per user spec (C2) — gate must block newcomers AND existing gamers. Placing it before role resolution is the simplest single checkpoint that covers every path.
**Config:** `required_chat_id` in MongoDB `config` collection (negative integer, `None` = disabled). Editable via superadmin config editor.
**Fail-open:** Any API exception from `get_chat_member` is swallowed — user is never blocked due to Telegram API errors.
**Blocked statuses:** `left`, `kicked`, `banned`. All other statuses (`member`, `administrator`, `creator`, `restricted`) pass through.
**Rollback:** Set `required_chat_id` to `None` via config editor → gate disabled immediately, no deploy needed.

## Sprint B/C: UUID invite tokens replace integer referral links

**Decision:** `invite_tokens` collection maps `uuid` (UUID4 string) → `issuer_id` (Telegram user ID) + `role_type`. `/start?start=<uuid>` looks up token instead of treating the param as a raw integer user_id.
**Reason:** Raw integer user IDs in deep links are a security/enumeration risk. UUID4 tokens are unguessable. Also fixes the old `gamer_referral_link` handler which was still generating broken `?start={user_id}` links.
**Idempotent:** `ensure_invite_token(issuer_id, role_type)` creates-or-returns; TOCTOU DuplicateKeyError handled by re-fetch.
**Rollback:** Revert `/start` handler to `parts[1].isdigit()` check and drop `invite_tokens` collection.

## Config editor: int() try/except replaces isdigit() for integer fields

**Decision:** `_is_valid_int(s)` uses `try: int(s) / except ValueError` instead of `s.lstrip('-').isdigit()`.
**Reason:** `lstrip('-').isdigit()` incorrectly accepted `"--1"` (strips all leading dashes → `"1"` passes isdigit, but `int("--1")` raises ValueError). `required_chat_id` values are large negative integers so this path is now exercised in production.
**Rollback:** Not recommended — old pattern is strictly worse.
