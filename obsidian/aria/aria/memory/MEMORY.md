# Memory Index — Aria Project

> **Primary memory store for Claude sessions on this project.**
> Read this file first via Obsidian MCP at the start of every session.

## Memory Map

- [[memory/project_aria|Project: Aria]] — Stack, architecture, season state (S4 live), deployment targets, known gaps
- [[memory/feedback_aria_workflow|Workflow & Coding Rules]] — Deploy split, safe_wrap, message cleanup, ObjectId pattern, MarkdownV2 escaping, handler checklist, **Superpowers skill usage guide**
- [[memory/reference_aria_codebase|Codebase Reference]] — Where things live in code, env vars, MongoDB collections, Sheets column layout

## Boot Protocol

When starting a new Aria session:
1. `mcp__obsidian__vault_read path="aria/memory/MEMORY.md"` — this file
2. `mcp__obsidian__vault_read path="aria/memory/project_aria.md"` — season state, gaps, deployment
3. `mcp__obsidian__vault_read path="aria/memory/feedback_aria_workflow.md"` — patterns + Superpowers skill map
4. For file locations or IDs → `mcp__obsidian__vault_read path="aria/memory/reference_aria_codebase.md"`
5. For latest implementation status → `mcp__obsidian__vault_read path="aria/REVIEW.md"`

## Quick Rules

- **Never push to git or deploy** — user does this manually after Cowork review
- All Telegram API calls → `utils.safe_wrap(lambda: ...)`
- All screen transitions → `add_message_history` / `clean_messages` / send / `add_message_history`
- All account `callback_data` → ObjectId hex (24 chars), never profile names
- All dynamic content in MarkdownV2 → `utils.escape()` — including `+`, `-`, `.` in numbers/dates
- Lambda closures in loops → `lambda x=x:` to capture by value, not reference
- `callback_query.answer("")` → FIRST line of every callback handler, before any DB work
- After any feature → update `CLAUDE.md` + Obsidian vault (`docs/` in codebase is deprecated)
- **All specs/plans → Obsidian vault** (`aria/docs/specs/` and `aria/docs/plans/`) + cross-link from `[[NEXT]]`
- **Run `brain-search` before writing any plan or spec** — gather context first

## Superpowers Skill Quick Reference

| Situation | Skill |
|---|---|
| New feature design | `superpowers:brainstorming` → `superpowers:writing-plans` |
| Plan execution | `superpowers:subagent-driven-development` |
| Any bug/unexpected behavior | `superpowers:systematic-debugging` |
| Before claiming done | `superpowers:verification-before-completion` (show pytest output) |
| New code / bugfix | `superpowers:test-driven-development` (failing test first) |

Full guide with Aria-specific application → [[memory/feedback_aria_workflow]]

## Session Handoff

Last session: 2026-05-28 (Sprint F + test fixes complete)
Last brain-save: 2026-05-28

**Current focus: All tests fixed. Ready for user to commit B+C+D+F together.**

**Uncommitted sprints in working tree (all code written, tests written, NO git commits):**
- Sprint B — Invite tokens (B1–B8)
- Sprint C — Chat membership gate (C1–C4)
- Sprint D — Support dashboard (D1–D6) + 3 code-review fixes
- Sprint F — Gamer scale & performance (F1–F5)
- **Test fixes** — 18 originally failing tests + 2 code-review fixes applied to test files

**Sprint F changes (on top of B+C+D):**
- `mongodb.py` — `get_open_support_tasks` uses `$lookup` pipeline (+ `r.setdefault("gamer", None)` for mongomock compat); `get_all_gamers_season_points` has 60s TTL cache
- `main.py` — `ACCOUNT_PAGE_SIZE=10`, `RELEASE_PAGE_SIZE=10` (lines 30–31); `_build_account_page()` (line ~150); `_build_release_page()` (line ~231); `account_page_nav` callback (line ~713); `release_page_nav` callback (line ~882); `asyncio.gather` role resolution (line ~297)
- `texts.py` — `gamer_account_page_header` template
- `tests/test_sprint_f.py` — 9 tests (F1×3, F2×1, F3×2, F5×2)
- `tests/test_sprint_d.py` — `aggregate()` method added to `_AsyncCollection`

**Test fixes applied (2026-05-28):**
- `mongodb.py` — added `r.setdefault("gamer", None)` after `$lookup` aggregate (mongomock compat)
- `tests/test_gamer_handlers.py` — `test_account_screen_shows_active_emoji`: state mock needs `state.update_data = AsyncMock()`
- `tests/test_invite_tokens.py` — added `_TelegramStateMock` + `get_config` mock in `_make_start_db`; fixed `assert "referral\\-uuid\\-abc"` (UUID escapes `-` to `\-`)
- `tests/test_membership_gate.py` (new) — added `_TelegramStateMock`; all gate tests patch `main.TelegramState`
- `tests/test_sprint_d.py` — added `_TelegramStateMock`; profile `"myprofile"` (no underscores); async `_fake_safe_wrap` in all 3 `safe_wrap` spies; patched both `main.safe_wrap` + `utils.safe_wrap` for release test

**Sprint order:** A ✅ → E ✅ → B ✅ (commit pending) → C ✅ (commit pending) → D ✅ (commit pending) → **F ✅ (commit pending)**

**Test suite state (~130 tests total):**
- `tests/test_invite_tokens.py` — 16 tests (Sprint B)
- `tests/test_membership_gate.py` — 10 tests (Sprint C)
- `tests/test_sprint_d.py` — 16 tests (Sprint D + fixes)
- `tests/test_sprint_f.py` — 9 tests (Sprint F)
- `tests/test_mongodb_sprint_e.py` — 8 tests (Sprint E)
- `tests/test_gamer_handlers.py` — 18 tests (Sprint E + fix)
- `tests/test_message_format.py` — 14 tests (Sprint E)
- `tests/test_load_and_race.py` — 8 tests (Sprint E)

**User manual actions needed:**
- Run `pytest tests/ -v` (install: `pip install mongomock pytest pytest-asyncio --break-system-packages`)
- Run `rm -rf /Users/ivan/Work/aria/docs` (docs/ folder deprecated — content migrated to Obsidian vault)
- Commit all uncommitted sprints

**Critical warnings for next session:**
- **Never run `git commit`, `git push`, or `npm run deploy-*` — user does this manually**
- Always read `aria/memory/MEMORY.md` + three linked files BEFORE any code work
- Use Superpowers skills as described in [[memory/feedback_aria_workflow]]
- Sprint A complete — do not re-implement admin/operator anything
- Sprint E: `release_approve` callback removed — stale inline buttons → "already processed"
- Before running `pytest tests/ -v`, install: `pip install mongomock pytest pytest-asyncio --break-system-packages`
- Sprint C gate applies to ALL users including superadmins/support (by design, per user spec)
- `required_chat_id` is a negative integer (Telegram group ID) — e.g. `-100123456789`
- Motor API: `collection.find(query)` is SYNC → `cursor.to_list(n)` is ASYNC. Test helpers must use `_AsyncCursor` wrapper, NOT `async def find` (returns coroutine with no `.to_list`)
- `edit_message_text` without `reply_markup=` leaves stale inline buttons — always pass explicit empty markup when clearing
- `db.is_gamer()` takes a dict `{"id": uid}`, NOT a bare integer
- **All new specs/plans → Obsidian vault** (`aria/docs/specs/` and `aria/docs/plans/`). `docs/` codebase folder is deprecated.

## Related Vault Docs

[[INDEX]] · [[CONTEXT]] · [[DECISIONS]] · [[PROGRESS]] · [[REVIEW]] · [[NEXT]]
