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
Last brain-save: 2026-05-27

**Current focus: Sprint B — fully done. Ready for user to commit.**

**Sprint B status: code written + reviewed + tested (NOT YET COMMITTED — user commits manually)**

**All Sprint B changes in working tree (unstaged vs committed Sprint B):**
- `main.py` — safe_wrap lambda fix, message cleanup, disable_web_page_preview, ensure_invite_token for new superadmins, `gamer_referral_link` now uses UUID token instead of raw user_id
- `tests/test_invite_tokens.py` — untracked (16 tests, not yet committed)
- `buttons.py`, `markups.py`, `texts.py`, `mongodb.py` — Sprint B changes vs HEAD

**Test suite state: 16 tests in test_invite_tokens.py**
- 5 DB method tests (ensure/get token, TOCTOU race)
- 2 /start handler tests (real handler calls)
- 2 admin_added handler tests (support + superadmin token creation)
- 6 invite link handler tests (3 roles × callable check + cleanup check)
- 1 gamer_referral_link test (confirms UUID token used, not raw user_id)

**Design decision made (2026-05-27):**
- Old `gamer_referral_link` (buttons.referral) updated to use UUID tokens (option b)
- Both referral buttons on gamer home now use the same UUID mechanism
- The `bot.get_me()` call in that handler replaced with `BOT_USERNAME` global

**Sprint order:** Sprint A ✅ → Sprint E ✅ → Sprint E tests ✅ → **B (✅ complete, commit pending)** → C → D

**Critical warnings for next session:**
- **Never run `git commit` — user commits manually after reviewing**
- Always read `aria/memory/MEMORY.md` + three linked files BEFORE any code work
- Use Superpowers skills as described in [[memory/feedback_aria_workflow]]
- Sprint A is complete — do not re-implement admin/operator anything
- Sprint E: `release_approve` callback removed — old bots/clients with stale inline buttons will get "already processed" message
- Before running `pytest tests/ -v`, install: `pip install mongomock --break-system-packages`

## Related Vault Docs

[[INDEX]] · [[CONTEXT]] · [[DECISIONS]] · [[PROGRESS]] · [[REVIEW]] · [[NEXT]]
