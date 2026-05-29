# Sprint F — Gamer Scale & Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix silent account-screen overflow at 15-20 accounts, paginate the release selector, replace N+1 queries with aggregation, parallelize role resolution, and add leaderboard TTL cache.

**Architecture:** DB-layer changes first (Tasks 1–2), then core `start()` fix (Task 3), then gamer UI changes (Tasks 4–5). Each task is independently testable. No new FSM states required. All Telegram API calls remain wrapped in `safe_wrap`. No git commits — user commits manually after tests pass.

**Tech Stack:** Python 3, aiogram 2.x, Motor (async MongoDB), mongomock (tests), pytest-asyncio.

**Spec:** `aria/docs/specs/2026-05-28-sprint-f-gamer-scale-design.md` in the Obsidian vault.

**⚠️ CRITICAL RULES:**
- Never run `git commit`, `git push`, or `npm run deploy-*` — user commits manually
- Every Telegram API call → `safe_wrap(lambda: ...)`
- Every screen transition → `add_message_history` / `clean_messages` / send / `add_message_history`
- `callback_query.answer("")` must be the FIRST await in every callback handler
- All dynamic content in MarkdownV2 messages → `utils.escape()`
- Run `pip install mongomock --break-system-packages` before running tests

---

## File Map

| File | Changes |
|---|---|
| `mongodb.py` | Replace `get_open_support_tasks` body with `$lookup` aggregation (F3); add `_leaderboard_cache` + TTL guard to `get_all_gamers_season_points` (F5) |
| `main.py` | Add `_build_account_page()` helper; rewrite `gamer_account` to paginate; add `account_page` callback; add `_build_release_page()` helper; rewrite `gamer_release_account_prompt` to paginate; add `release_page` callback; parallelize `start()` role resolution (F4) |
| `texts.py` | Add `gamer_account_page_header` template (paginated header without `accounts_table`) |
| `tests/test_sprint_f.py` | New file — 8 tests covering all tasks |

---

See full plan with all code: [[docs/plans/2026-05-28-sprint-f-gamer-scale-plan]]
