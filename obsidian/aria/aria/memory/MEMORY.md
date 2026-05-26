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
- After any feature → update `CLAUDE.md` + relevant `docs/` file + Obsidian vault

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

Last session: 2026-05-27
Interrupted task: clean exit — all tests passing, brain-save complete
Last brain-save: 2026-05-27

**Current focus: Sprint B (invite token system)**

Test suite state: **85 tests, all passing**
- `tests/test_mongodb_eligibility.py` — 1 (ban check)
- `tests/test_mongodb_sprint_e.py` — 8 (new Sprint E methods)
- `tests/test_gamer_handlers.py` — 18 (pickup/release/account-screen handlers)
- `tests/test_message_format.py` — 14 (MarkdownV2 + message length)
- `tests/test_load_and_race.py` — 8 (25-account load + race conditions)
- `tests/test_progress_monitor.py` — existing (inactivity escalation)
- `tests/conftest.py` — shared: `assert_valid_markdownv2()`, `make_fake_account()`, `make_fake_gamer()`

Key design decisions (Sprint E — complete ✅):
- Two support actions: "🔓 В пул" (`release_pool`) and "🚫 Закрыть навсегда" (`release_finish`)
- On-demand: 3 buttons (pool + finish + deny); Inactivity: 2 buttons (pool + finish, no deny)
- New `release_blocks` collection: compound unique `(account_id, gamer_id)`
- `gamers.pool_release_count >= 5` → gamer banned from pickup
- Progress history in notifications: filtered by `entry.gamer_id == gamer._id`
- `sync_single_account` triggered when account enters `pending_release`
- `add_release_block` catches bare `Exception` (not just DuplicateKeyError); timestamp = `blocked_at`

**Sprint order:** Sprint A ✅ → Sprint E ✅ → Sprint E tests ✅ → **B** → C → D

**Critical warnings for next session:**
- Always read `aria/memory/MEMORY.md` + three linked files BEFORE any code work
- Use Superpowers skills as described in [[memory/feedback_aria_workflow]]
- `sheet_synchonizer` is credentials-only — `sync_single_account` is the only new method
- Sprint A is complete — do not re-implement admin/operator anything
- Sprint E: `release_approve` callback removed — old bots/clients with stale inline buttons will get "already processed" message
- Before running `pytest tests/ -v`, install: `pip install mongomock --break-system-packages`

## Related Vault Docs

[[INDEX]] · [[CONTEXT]] · [[DECISIONS]] · [[PROGRESS]] · [[REVIEW]] · [[NEXT]]
