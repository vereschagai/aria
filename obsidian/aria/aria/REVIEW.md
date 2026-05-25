# Design Chat → Implementation Review

Maps every request and design decision from the design chat to its implementation status in the codebase.

**Status legend:**
- ✅ Implemented — in code, working
- 🔧 Fixed — was broken, corrected in code review
- ⚠️ Partial — implemented but with known gaps or caveats
- ❌ Missing — designed but not implemented
- 📝 Docs only — decision documented, no code needed

---

## Tech Debt and Cleanup

| Request | Status | Notes |
|---|---|---|
| Clean up `requirements.txt` — remove unused packages (Flask, numpy, pyppeteer, phonenumbers, etc.) | ✅ | 23 remaining packages, all relevant |
| Fix `cryptoaddress===0.2.1` invalid pip syntax → `==` | ✅ | Fixed |
| Move `client_secret.json` out of repo history (BFG/filter-branch) | ❌ | **Not done.** File is gitignored but still present in repo directory and likely in git history. Needs `git filter-branch` or BFG Repo Cleaner run. |
| Move bot token to env var, no hardcoded fallback | 🔧 | Fixed in code review — `main.py` now raises `RuntimeError` if `BOT_TOKEN` is unset |
| Remove dead `self.loop = asyncio.new_event_loop()` from `google_api.py` | 🔧 | Fixed in code review |
| Add `if __name__ == "__main__":` guard to `mongo_scripts.py` | ✅ | Already present |
| Add `deployment.config.js.example` for onboarding | ✅ | Present in repo |
| Rewrite `CLAUDE.md` as shared context bridge for Claude Code sessions | ✅ | Present and up to date |
| Create `docs/` directory with architecture, data model, flow, feature docs | ✅ | 6 docs present: `architecture.md`, `data-model.md`, `adding-features.md`, `flows.md`, `season3-system-design.md`, `season4-system-design.md` |
| Fix `min_progress_points` default inconsistency (10 vs 50) | 🔧 | Fixed in code review — `config.py` now seeds 50 |
| Remove dead `is_new_year` param from leaderboard renderer | 🔧 | Fixed in code review |
| Move hardcoded `"Че нада?"` string to `texts.py` | 🔧 | Fixed in code review |
| Remove `aiocron` if unused | ⚠️ | Still in `requirements.txt`. Chat flagged it as potentially unused but it was not removed. Verify whether `@cron` decorators are used anywhere in the codebase. |
| Fix `inactivity_day_buffer_hours` dead field | ⚠️ | Field kept in `config.py` and seeded to DB "for backwards compat." No code reads it. Could be removed from config seed and DB safely. |

---

## Season 3 System Design

### Gamer ID Binding

| Request | Status | Notes |
|---|---|---|
| Replace gamer username strings with MongoDB ObjectId (`gamer_id`) throughout | ✅ | `ownership_history[].gamer_id` and `progress_history[].gamer_id` both use ObjectId |
| Add `get_account_by_object_id()` for callback lookup | ✅ | Present in `mongodb.py` |
| Use account `_id` hex in Telegram `callback_data` (not profile name) to stay under 64-byte limit | ✅ | Implemented in all account-related callbacks |

### Progress History

| Request | Status | Notes |
|---|---|---|
| Per-sync `progress_history` array: `{synced_at, tower_points, delta, gamer_id}` | ✅ | Appended in `sheet_synchonizer.grab_accounts()` |
| Delta = `new_tower_points - progress_history[-1].tower_points` (no special-case for start) | ✅ | Implemented |
| Attribute delta to current `gamer_id` (null if in pool) | ✅ | `gamer_id` from account document at time of sync |
| `last_progress_at` updated only when delta > 0 | ✅ | Implemented in synchonizer |

### Sheet Sync Rewrite (Option C)

| Request | Status | Notes |
|---|---|---|
| New column layout: `[0]` profile, `[1]` login, `[2]` password, `[3]` proxy, `[5]` active, `[6]` gamer (ignored), `[7]` TP Start, `[8+]` daily | ✅ | Implemented |
| Parse `points;rank;floor` format (3 values, not 5) | ✅ | `__parse_tower()` handles 3-value format |
| Skip rows: Active == `#N/A`, Proxy == `#N/A`, row < 6 cols | ✅ | Implemented |
| Handle `NaN;NaN;NaN` in tower point fields | ✅ | `__parse_tower()` detects NaN, returns zeros |
| Never read or write `gamer` column (Option C) | ✅ | Confirmed — no `gamer_id` writes in synchonizer |
| New accounts inserted as `status: "released"`, seed progress_history from TP Start | ✅ | Implemented (Season 4 format) |

### Inactivity Monitor

| Request | Status | Notes |
|---|---|---|
| Calendar-day inactivity: `(today - baseline.date()).days` | ✅ | Implemented in `progress_monitor.py` |
| Day 1–2: warning message to gamer | ✅ | `_warn_gamer()` |
| Day 3+: escalate to all support users with last-5-progress card + inline buttons | ✅ | `_escalate()` |
| Escalated accounts excluded from warning loop (`elif` guard) | ✅ | Implemented |
| `pending_release` accounts excluded from inactivity check | ✅ | Implemented |
| Per-day deduplication via `last_notified_day` ordinal | ✅ | Implemented |
| Stub gamers (no Telegram ID) safely skipped | ✅ | Checked via `gamer.get("id")` |

### Support Role

| Request | Status | Notes |
|---|---|---|
| New support role between operator and gamer | ✅ | In role hierarchy, FSM, DB collection |
| Add/remove support via Telegram contact (same as operator) | ✅ | `admin_add_support` flow |
| Support receives escalation cards | ✅ | `progress_monitor._escalate()` sends to all support users |
| Support receives release requests | ✅ | `gamer_release_account_select()` notifies all support users |
| Support decision: progress possible → release to pool | ✅ | `support_decision()` callback |
| Support decision: no progress → mark inactive | ✅ | `support_decision()` callback |
| Support decision for on-demand release: approve/deny | ✅ | `support_release_decision()` callback |

### Account Eligibility

| Request | Status | Notes |
|---|---|---|
| Slot limit check: `count_gamer_accounts() < max_accounts_per_gamer` | ✅ | In `check_assignment_eligibility()` |
| Progress check: every active account's last entry under this gamer has `delta >= min_progress_points` | ✅ | Implemented |
| Empty `progress_history` skipped (newly assigned) | ✅ | Handled |
| `pending_release` counted toward slot, excluded from progress check | ✅ | Handled |
| Escalated accounts: count toward slot but do NOT block eligibility | ✅ | Implemented (design decision reversed from original) |

### Gamer Season Points Display

| Request | Status | Notes |
|---|---|---|
| Show season points on gamer account screen | ✅ | `gamer_account()` calls `get_gamer_season_points()` |
| Season points = sum of positive deltas attributed to this gamer across all accounts | ✅ | Aggregation pipeline in `mongodb.py` |

### On-Demand Release

| Request | Status | Notes |
|---|---|---|
| "🔓 Освободить аккаунт" button on gamer home | ✅ | Implemented |
| Shows inline list of active accounts | ✅ | `gamer_release_account_prompt()` |
| Sets `status: "pending_release"` | ✅ | `request_account_release()` |
| Notifies all support users with approve/deny inline keyboard | ✅ | Implemented |
| Support approval → account to pool, gamer notified | ✅ | `support_release_decision()` |
| Support denial → account stays active, gamer notified | ✅ | Implemented |

### Migration Season 3

| Request | Status | Notes |
|---|---|---|
| `migration_season3.py` — snapshot `season3_start_points`, bind `gamer_id` by username, init `ownership_history` and `progress_history`, seed config | ✅ | Script present. Already applied to production — do not re-run. |
| Idempotency check on `season3_start_points` field | ✅ | Present |

---

## Season 4 System Design

### Account Model Changes

| Request | Status | Notes |
|---|---|---|
| Replace `season3_start_points` with seed `progress_history` entry (`delta = starting_tower_points`, `gamer_id = <owner at migration>`) | 🔧 | Implemented in `migration_season4.py`. **Critical bug fixed in code review**: `gamer_id` was hardcoded as `None` instead of `account.get("gamer_id")`. |
| Remove `available_for_pickup` field — derive from `status == "released"` | ✅ | No references outside migrations. All queries use `status` |
| All accounts start Season 4 as `status: "released"`, `gamer_id: null` | ✅ | `migration_season4.py` resets all accounts |
| Sparse fields (`pending_proof`, `release_request`) — `$unset` on release, never initialized to null | ✅ | `release_account()` uses `$unset` |

### Self-Service Pickup

| Request | Status | Notes |
|---|---|---|
| "🎮 Взять аккаунт" button replaces "📥 Запросить аккаунт" | ✅ | `gamer_pickup_account()` handler |
| No list shown to gamer — fully automatic assignment | ✅ | Implemented |
| Priority 1: accounts with this gamer in `ownership_history`, sorted desc by points | ✅ | `pickup_account()` |
| Priority 2: released accounts whose last owner has `season_picked_up != True` | ✅ | `pickup_account()` |
| Atomic `findOneAndUpdate` with `status == "released"` guard | ✅ | Implemented |
| `season_picked_up` flag set on first pickup | ✅ | `mark_gamer_season_active()` |
| No `picked_up_at` field — eligibility via `progress_history[-1].gamer_id` | ✅ | Implemented |

### Migration Season 4

| Request | Status | Notes |
|---|---|---|
| `migration_season4.py` — create seed entries, close ownership history, reset to pool, `$unset` legacy fields | ✅ | Script present. Already applied to production — do not re-run. |
| Idempotency check on `season3_start_points.$exists` | ✅ | Present |
| Rollback scripts in `package.json` | ✅ | `rollback-prod`, `rollback-qa` present |

---

## Open Issues (not addressed in any session)

| Issue | Priority | Notes |
|---|---|---|
| `client_secret.json` in git history | High | BFG Repo Cleaner or `git filter-branch --index-filter` needed |
| `google_api.py` blocks asyncio event loop during Sheets sync | Medium | ✅ Fixed — `get_accounts()` is now `async`; blocking HTTP call wrapped in `loop.run_in_executor(None, ...)`. `sheet_synchonizer.py` updated to `await` the call. |
| `@goldalfsupp` hardcoded in `texts.py` line 184 | Low | ✅ Fixed — `texts.py` uses `{support_handle}` template. `config.py` seeds `support_handle: "@goldalfsupp"`. `gamer_account` handler in `main.py` fetches from `db.get_config()` and passes through `utils.escape()`. |
| Superadmin Telegram ID hardcoded in `main.py` | Low | By design (seeded to DB on startup), but requires code change to add a second superadmin. |
| Google Sheet ID hardcoded in `main.py` | Low | ✅ Fixed — moved to `ARIA_SHEET_ID` env var with `RuntimeError` if unset (same pattern as `BOT_TOKEN`). |
| No automated tests | Low | No test files anywhere in repo. |
| `aiocron` in `requirements.txt` — verify if actually used | Low | Flagged in design chat as potentially unused. |
| `inactivity_day_buffer_hours` dead config field | Low | ✅ Fixed — removed from `config.py` seed. Migration scripts left untouched. Field will remain in existing DB documents but is not seeded on new instances. |
| `ws_resolver.js` must be started with `INCLUDE_METAMASK=true` | Medium | ✅ Fixed — wallet tasks fail fast with a clear error if `METAMASK_PATH` is unset; `METAMASK_REQUIRED_TASK_TYPES` set added to `ws_resolver.js` |
| `_ariaMetamaskCache` — single-flight only keyed per profileName | Medium | ✅ Fixed — replaced per-profile in-flight map with a single shared `_ariaSheetInflight` module-level promise; any cache miss awaits the same in-flight read |
| `ws_stabilizer.js` only restarts on non-"Target closed" exit | Medium | ✅ Fixed — restart condition removed; process now always restarts on exit regardless of stderr content |
