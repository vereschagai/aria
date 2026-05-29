# NEXT — Pre-Launch Feature Sprint

> Last updated: 2026-05-28. Sprint A completed 2026-05-26. Sprint E designed 2026-05-26.
> Full design rationale in [[memory/MEMORY]] session handoff.
>
> Execution order: Sprint A (done) → Sprint E (in progress) → B → C → D → F.
> Implementation workflow per task: brain-search → (design if feature) → implement → dry-test → code review → update docs → commit.

---

## Sprint A — Role Cleanup ✅ COMPLETE

Remove unused `admin` and `operator` roles entirely. Support inherits leaderboard.
**No DB migration needed** — neither collection was ever populated in production.

| # | Task | Files | Status |
|---|---|---|---|
| A1 | Delete `operator_controller.py`; remove import and `init_handlers()` call | main.py, operator_controller.py | ✅ |
| A2 | Remove all operator FSM states from `state.py` | state.py | ✅ |
| A3 | Remove operator handlers from `main.py` | main.py | ✅ |
| A4 | Remove operator DB methods from `mongodb.py` | mongodb.py | ✅ |
| A5 | Remove admin FSM states from `state.py` | state.py | ✅ |
| A6 | Remove admin handlers from `main.py` | main.py | ✅ |
| A7 | Remove admin DB methods from `mongodb.py` | mongodb.py | ✅ |
| A8 | Remove admin/operator strings, buttons, markups | texts.py, buttons.py, markups.py | ✅ |
| A9 | Extract leaderboard → support home "🏆 Лидерборд" button | main.py, buttons.py, markups.py | ✅ |
| A10 | Update role resolution in `start()` — superadmin → support → gamer | main.py | ✅ |

---

## Sprint E — Release Flow Redesign ✅ COMPLETE

Redesign the on-demand account release flow: two support actions (pool release vs permanent close),
gamer ban after 5 pool releases, account-gamer block on released accounts, filtered progress history,
and a finished accounts list for support/superadmin.

**New collection:** `release_blocks { account_id: ObjectId, gamer_id: ObjectId, blocked_at, reason }`
**New account status:** `finished` — permanent close, unplayable for the season
**New gamer field:** `pool_release_count: int` — ban when >= 5

See full design: [[flows/on-demand-release]]

| # | Task | Files | Status |
|---|---|---|---|
| E1 | Add `release_blocks` collection + index to `ensure_indexes()` | mongodb.py | ✅ |
| E2 | Add `gamers.pool_release_count` field (default 0) | mongodb.py, migration | ✅ |
| E3 | Add `accounts.status == "finished"` support + `finished_at`, `finished_by`, `final_tower_points` fields | mongodb.py | ✅ |
| E4 | New mongodb methods: `add_release_block`, `get_gamer_release_block_ids`, `increment_pool_release_count`, `finish_account`, `get_finished_accounts` | mongodb.py | ✅ |
| E5 | Update `pickup_account`: fetch blocked account IDs for gamer, exclude with `$nin`; add ban check (`pool_release_count >= 5`) to `check_assignment_eligibility` | mongodb.py | ✅ |
| E6 | New `sync_single_account(profile)` method in `sheet_synchonizer.py` | sheet_synchonizer.py | ✅ |
| E7 | Update `gamer_release_account_select`: filter progress_history by `gamer_id`, trigger `sync_single_account`, use new 3-button markup (on-demand), `callback_query.answer("")` first | main.py | ✅ |
| E8 | Rewrite `support_release_decision`: handle `release_pool`, `release_finish`, `release_deny` callbacks | main.py | ✅ |
| E9 | Update `progress_monitor.py` escalation: filter progress by gamer_id, 2-button markup (no deny) | progress_monitor.py | ✅ |
| E10 | Add new texts + buttons for pool/finish/deny flow | texts.py, buttons.py | ✅ |
| E11 | Add "📋 Закрытые аккаунты" button + handler | main.py, buttons.py, markups.py, texts.py | ✅ |

---

## Sprint E Tests ✅ COMPLETE

85 total tests passing (was 37 pre-Sprint E). New files:

| File | Tests | Covers |
|---|---|---|
| `tests/test_mongodb_sprint_e.py` | 8 | `add_release_block`, `get_gamer_release_block_ids`, `increment_pool_release_count`, `finish_account`, `get_finished_accounts`, `$nin` exclusion |
| `tests/test_gamer_handlers.py` | 18 | Pickup/release/account-screen handler behavior with aiogram + AsyncMock |
| `tests/test_message_format.py` | 14 | MarkdownV2 char-by-char validator, `utils.escape()` unit tests, 4096-char limits, callback data length |
| `tests/test_load_and_race.py` | 8 | 25-account load tests, simultaneous pickup race with asyncio.gather + mongomock |
| `tests/conftest.py` | — | `assert_valid_markdownv2()`, `make_fake_account()`, `make_fake_gamer()` helpers |

**Key test patterns discovered:**
- `TelegramState` mocking: `_TelegramStateMock` with `async def set()` on every attribute
- Race condition tests: asyncio cooperative scheduling + `claimed[0]` closure as atomic flag
- `add_release_block` catches bare `Exception` (not just `DuplicateKeyError`) — timestamp field is `blocked_at`
- MarkdownV2 validator allows `*_~` bare (formatting markers), requires `+-./!()[]{}#=|>` escaped

## Sprint B — Invite Token System ✅ COMPLETE (commit pending)

Replace raw Telegram IDs in `?start=` links with persistent UUID tokens stored in MongoDB.
Each inviter (superadmin, support, gamer) has exactly one token. Old `gamer_referral_link` updated to use UUID token too.

**New collection:** `invite_tokens { uuid: String (unique), issuer_id: Int, role_type: "superadmin"|"support"|"gamer", created_at: DateTime }`

| # | Task | Files | Status |
|---|---|---|---|
| B1 | Add `invite_tokens` collection index (`uuid` unique, `issuer_id` unique) to `ensure_indexes()` | mongodb.py | ✅ |
| B2 | Add MongoDb methods: `ensure_invite_token(issuer_id, role_type)`, `get_invite_token_by_uuid(uuid)` | mongodb.py | ✅ |
| B3 | On bot startup: call `ensure_invite_token(SUPERADMIN_ID, "superadmin")` | main.py | ✅ |
| B4 | Replace referral validity check with UUID lookup | main.py | ✅ |
| B5 | Superadmin home: "🔗 Ссылка для приглашения" → `t.me/<bot>?start=<uuid>` | main.py, buttons.py, markups.py, texts.py | ✅ |
| B6 | In `add_support` flow: call `ensure_invite_token(contact.user_id, "support")` | main.py | ✅ |
| B7 | Support home: "🔗 Пригласить игрока" button | main.py, buttons.py, markups.py, texts.py | ✅ |
| B8 | Gamer home: "👥 Пригласить друга" button + UUID referral link | main.py, buttons.py, markups.py, texts.py | ✅ |

**Tests:** `tests/test_invite_tokens.py` — 16 tests (DB methods, /start handler, admin_added, invite link handlers, gamer_referral_link)

**⚠️ NOT YET COMMITTED — user commits manually**

## Sprint C — Chat Membership Gate ✅ COMPLETE (commit pending)

Optional bot membership check against guild chat. Config key: `required_chat_id` (null = disabled). Fails open.
Gate fires before role resolution — applies to ALL users (superadmins, support, gamers).

| # | Task | Files | Status |
|---|---|---|---|
| C1 | Add `required_chat_id: None` to config seed | config.py | ✅ |
| C2 | In `/start`: check `get_chat_member` for ALL users if `required_chat_id` set; fail open on exceptions; blocks `left/kicked/banned` | main.py | ✅ |
| C3 | Add `texts.gamer_not_in_chat` | texts.py | ✅ |
| C4 | Config editor handles negative integers via `_is_valid_int()` (try/except) — replaces broken `lstrip('-').isdigit()` | main.py | ✅ |

**Tests:** `tests/test_membership_gate.py` — 10 tests (blocked ×3, allowed ×4, fail-open, disabled ×2, config editor ×4)

**⚠️ NOT YET COMMITTED — user commits manually**

## Sprint D — Support Dashboard ✅ COMPLETE (commit pending)

Central screen for open escalations and release requests with inline action + DM buttons.

| # | Task | Files | Status |
|---|---|---|---|
| D1 | `get_open_support_tasks()` — escalated + pending_release with gamer info joined | mongodb.py | ✅ |
| D2 | `support_dashboard` FSM state + `support_tasks` button + markups + empty text | state.py, buttons.py, markups.py, texts.py | ✅ |
| D3 | `_build_dashboard_page()` + `support_dashboard_open` + `dashboard_paginate` | main.py | ✅ |
| D4 | "📋 Задачи" button on support home + superadmin home (read-only for SA) | main.py, markups.py | ✅ |
| D5 | Existing `release_pool/finish/deny` callbacks work from dashboard (state="*") | main.py | ✅ (no change needed) |
| D6 | DM URL button in `_escalate()` + in `gamer_release_account_select` notification | progress_monitor.py, main.py | ✅ |

**Code review fixes:** inline KB cleared on empty-tasks paginate; message tracking added to `support_dashboard_open`; `start()` clean_messages gap fixed for support/superadmin branches.
**16 tests** in `tests/test_sprint_d.py`. NOT YET COMMITTED — user commits manually.

---

## Sprint F — Gamer Scale & Performance ✅ COMPLETE (commit pending)

Design approved 2026-05-28. Spec: [[docs/specs/2026-05-28-sprint-f-gamer-scale-design|Sprint F Spec]].
Plan: [[docs/plans/2026-05-28-sprint-f-gamer-scale-plan|Sprint F Plan]].

| # | Task | Files | Status |
|---|---|---|---|
| F1 | Paginated gamer account screen (10/page, compact format, inline nav) | `main.py`, `texts.py` | ✅ |
| F2 | Paginated release account selector (10/page, inline nav) | `main.py` | ✅ |
| F3 | `get_open_support_tasks` → single `$lookup` aggregation | `mongodb.py` | ✅ |
| F4 | Parallel role resolution in `start()` via `asyncio.gather` | `main.py` | ✅ |
| F5 | Leaderboard TTL cache (60s, in-memory) | `mongodb.py` | ✅ |

**Sprint F changes in working tree (on top of B+C+D):**
- `mongodb.py` — `get_open_support_tasks` uses `$lookup` pipeline; `get_all_gamers_season_points` has 60s TTL cache (`_leaderboard_cache`, `LEADERBOARD_TTL_SECONDS`)
- `main.py` — `ACCOUNT_PAGE_SIZE=10`, `RELEASE_PAGE_SIZE=10` (lines 30–31); `_build_account_page()` (line 150); `_build_release_page()` (line 231); `account_page_nav` callback (line 713); `release_page_nav` callback (line 882); `asyncio.gather` role resolution (line 297)
- `texts.py` — `gamer_account_page_header` template added
- `tests/test_sprint_f.py` — 9 tests (F1 × 3, F2 × 1, F3 × 2, F5 × 2)
- `tests/test_sprint_d.py` — `aggregate()` method added to `_AsyncCollection` (compatible with new `$lookup` in `get_open_support_tasks`)

**⚠️ NOT YET COMMITTED — user commits manually**
**⚠️ User must also run: `rm -rf /Users/ivan/Work/aria/docs` (docs/ folder deprecated — content migrated to Obsidian vault)**

---

## Completed

- Sprint A — Role cleanup (all A1–A10) ✅
