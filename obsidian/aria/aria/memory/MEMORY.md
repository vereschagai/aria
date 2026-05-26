# Memory Index — Aria Project

> **Primary memory store for Claude sessions on this project.**
> Read this file first via Obsidian MCP at the start of every session.

## Memory Map

- [[memory/project_aria|Project: Aria]] — Stack, architecture, season state (S4 live), deployment targets, known gaps
- [[memory/feedback_aria_workflow|Workflow & Coding Rules]] — Deploy split, safe_wrap, message cleanup, ObjectId pattern, MarkdownV2 escaping, handler checklist
- [[memory/reference_aria_codebase|Codebase Reference]] — Where things live in code, env vars, MongoDB collections, Sheets column layout

## Boot Protocol

When starting a new Aria session:
1. `mcp__obsidian__vault_read path="aria/memory/MEMORY.md"` — this file
2. `mcp__obsidian__vault_read path="aria/memory/project_aria.md"` — season state, gaps, deployment
3. `mcp__obsidian__vault_read path="aria/memory/feedback_aria_workflow.md"` — patterns to follow
4. For file locations or IDs → `mcp__obsidian__vault_read path="aria/memory/reference_aria_codebase.md"`
5. For latest implementation status → `mcp__obsidian__vault_read path="aria/REVIEW.md"`

## Quick Rules

- **Never push to git or deploy** — user does this manually after Cowork review
- All Telegram API calls → `utils.safe_wrap(lambda: ...)`
- All screen transitions → `add_message_history` / `clean_messages` / send / `add_message_history`
- All account `callback_data` → ObjectId hex (24 chars), never profile names
- All dynamic content in MarkdownV2 → `utils.escape()`
- After any feature → update `CLAUDE.md` + relevant `docs/` file + Obsidian vault

## Session Handoff

Last session: 2026-05-26
Interrupted task: clean exit — pre-launch sprint designed
Last brain-save: 2026-05-26

**Next actions (see [[NEXT]] for full task list):**
- Sprint A (role cleanup) — remove admin + operator roles, support gets leaderboard
- Sprint B (invite tokens) — UUID-based invite links, no raw IDs
- Sprint C (chat gate) — optional membership check against guild chat
- Sprint D (support dashboard) — central screen for escalations + release requests

**Critical warnings for next session:**
- Always read `aria/memory/MEMORY.md` + three linked files BEFORE any code work
- Follow the 7-step Cowork workflow (brain-search → design → implement → dry-test → review → docs → commit)
- Use Engineering plugin skills for code-review, system-design, testing-strategy
- `sheet_synchonizer` is credentials-only — do NOT add side effects back
- Sprint A must complete before B/C/D — role resolution changes are a prerequisite

## Related Vault Docs

[[INDEX]] · [[CONTEXT]] · [[DECISIONS]] · [[PROGRESS]] · [[REVIEW]] · [[NEXT]]
