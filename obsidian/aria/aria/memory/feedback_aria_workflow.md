---
name: feedback-aria-workflow
description: Workflow rules for the Aria project — what Claude does vs. what the
  user does, and key coding patterns to always follow
type: feedback
updated: 2026-05-28
version: "8"
---

# Aria Project — Workflow & Coding Rules

See [[memory/project_aria|Project Overview]] for architecture context.

---

## Superpowers Plugin — Which Skills to Use When

The Superpowers plugin provides skills that enforce quality gates. Use them as described:

| Situation | Skill | When |
|---|---|---|
| New feature or behavior change | `superpowers:brainstorming` | BEFORE any design or implementation — full Q&A + design doc |
| Multi-step feature with a spec | `superpowers:writing-plans` | After brainstorming approval — produces `docs/superpowers/plans/YYYY-MM-DD-*.md` |
| Executing a plan with independent tasks | `superpowers:subagent-driven-development` | After writing-plans — dispatches fresh subagent per task with 2-stage review |
| Any bug, test failure, unexpected behavior | `superpowers:systematic-debugging` | BEFORE proposing any fix — 4-phase: Root Cause → Pattern → Hypothesis → Implementation |
| About to claim work is done or tests pass | `superpowers:verification-before-completion` | ALWAYS — run `python -m py_compile` + `pytest tests/ -v` and show output before claiming done |
| Any new feature or bugfix code | `superpowers:test-driven-development` | Write failing test FIRST, watch it fail, then implement minimal code |

### Aria-specific application

**For new sprints (B, C, D, etc.):** `brainstorming` → `writing-plans` → `subagent-driven-development`

**For bugs reported by user:** `systematic-debugging` (4-phase investigation) → `test-driven-development` (write failing test first) → `verification-before-completion` (show pytest output before reporting done)

**Test infrastructure:** ~130 test functions across `tests/` (sprint F + test fixes). Requires `mongomock` (`pip install mongomock pytest pytest-asyncio --break-system-packages`). Key test patterns:
- `assert_valid_markdownv2(text)` — char-by-char MarkdownV2 validator (conftest.py)
- `make_fake_account()` / `make_fake_gamer()` — realistic document builders (conftest.py)
- `_TelegramStateMock` / `_AsyncState` / `_ts()` — mock FSM state (defined locally in each test file)
- **`safe_wrap` spy pattern**: Use `async def _fake_safe_wrap(fn): return await fn()` + `AsyncMock(side_effect=_fake_safe_wrap)`. **NEVER** `AsyncMock(side_effect=lambda fn: fn())` for tests that rely on side-effects of nested async calls (e.g. `captured_markups`). The sync lambda returns the inner coroutine without awaiting it — `fake_send` never runs.

### Critical rules from skill definitions

- `callback_query.answer("")` must be the **first** await in every callback handler
- No fix attempt without root cause investigation first (systematic-debugging Phase 1)
- No production code without a failing test first (TDD iron law)
- No completion claim without fresh verification output — `pytest` must have been run in the same message
- Lambda closures in loops: `lambda x=x:` to capture by value

---

## Role split: Claude designs + codes, user deploys

Do NOT push to git or deploy. Commit, push, and deploy are done manually by the user after Cowork review.

**Why:** Production is live. Claude's role is design (Cowork) and implementation (Claude Code), never deployment.

**How to apply:** Never run `git push`, `npm run deploy-prod`, or `pm2 reload`. Hand off to the user with clear instructions.

---

## Always use safe_wrap for Telegram API calls

```python
sent = await utils.safe_wrap(lambda: message.answer("text", reply_markup=markups.start))
```

**Why:** Telegram API returns transient 429/5xx errors. Direct calls crash on rate limits. `safe_wrap` also swallows exceptions silently — which means a MarkdownV2 parse error will silently drop the message. Always check escaping when a message fails to send.

**How to apply:** Every `bot.send_message`, `message.answer`, `bot.edit_message_text`, etc. must be wrapped. See [[modules/utils]].

---

## Always track and clean messages on screen transitions

```python
await utils.add_message_history(db, message)     # track incoming
await utils.clean_messages(bot, db, user_id)      # delete previous batch
sent = await utils.safe_wrap(lambda: bot.send_message(...))
await utils.add_message_history(db, sent)         # track outgoing
```

**Why:** Without cleanup, old messages pile up and create confusing UX.

**How to apply:** Every screen transition — no exceptions. This includes handlers that change FSM state (like `support_dashboard_open`). The `start()` function branches for superadmin and support MUST also call `clean_messages` before sending the home screen.

**Sprint D fix:** `start()` superadmin/support branches never called `clean_messages` (pre-existing bug). Fixed — both branches now call `utils.clean_messages` before sending the home message.

**When sending multiple messages in one handler** (e.g. dashboard: reply-keyboard message + inline-keyboard message): track ALL sent messages with `add_message_history`, not just the last one.

---

## Always use ObjectId hex in callback_data — never profile names

```python
# Building keyboard:
callback_data=f"my_action:{str(account['_id'])}"

# In handler:
action, oid_str = callback_query.data.split(":", 1)
account = await db.get_account_by_object_id(ObjectId(oid_str))
```

**Why:** Telegram 64-byte `callback_data` limit. Profile names can exceed 50 chars and silently fail.

**How to apply:** Any new callback handler involving accounts. See [[DECISIONS#ObjectId hex in Telegram callback_data]].

---

## Always escape dynamic content in MarkdownV2 messages

```python
texts.some_template.format(username=utils.escape(gamer["username"]))
```

**Special cases that MUST be escaped** (frequently missed):
- `+` and `-` in numeric deltas: `utils.escape('+')`, `utils.escape(str(delta))`
- `.` in dates: pass the whole formatted string through `utils.escape(date_str)`
- Any integer or float converted to string: `utils.escape(str(number))`

**Why:** Unescaped `_`, `*`, `[`, `.`, `+`, `-`, etc. cause Telegram to silently reject the message. `safe_wrap` swallows the error and the message is never sent — this is how the release flow broke.

**How to apply:** All user-sourced strings (usernames, profile names, wallet addresses, numbers, dates) in MarkdownV2 templates. Static strings in `texts.py` are pre-escaped. See [[modules/texts]], [[modules/utils]].

---

## Guard gamer None before accessing fields

```python
gamer = await db.get_gamer(message.from_user.id)
if not gamer:
    return
```

**Why:** `db.get_gamer()` returns `None` for unregistered users. No guard → AttributeError.

---

## Adding a new handler — checklist

1. Add FSM states to `state.py` — see [[modules/state]]
2. Add button labels to `buttons.py`, markups to `markups.py`, strings to `texts.py`
3. Register in `main.py` with `@dp.message_handler(Text(equals=buttons.X), state=TelegramState.Y)`
4. If accessible from multiple roles, register once per relevant state
5. For account callbacks → ObjectId hex
6. **Update `CLAUDE.md` + relevant `docs/` file + Obsidian vault before implementing**
7. Write failing tests first (TDD) before implementing handler logic
8. Run `verification-before-completion` before marking task done

---

## Obsidian vault is the knowledge base of record

After any non-trivial implementation:
1. Update `CLAUDE.md` and relevant `docs/` file
2. Update vault: [[CONTEXT]], [[PROGRESS]], [[DECISIONS]] (new ADR if applicable)
3. Update affected [[modules/]] or [[flows/]] notes
4. Run brain-save to update session handoff in [[memory/MEMORY]]

**Why:** Without this, next session starts blind. Boot protocol reads these files first.

---

## Mandatory Cowork implementation workflow (updated with Superpowers)

Every non-trivial task must follow this sequence:

1. **brain-search** — search `aria/memory/` via Obsidian MCP before starting any work
2. **brainstorming** (`superpowers:brainstorming`) — for new features; produces design doc
3. **writing-plans** (`superpowers:writing-plans`) — produces step-by-step implementation plan
4. **Implement** — via `subagent-driven-development` or Claude Code with TDD
5. **verification-before-completion** — run `pytest tests/ -v`, show output
6. **Code review** — use `engineering:code-review` skill
7. **Fix vault docs** — update Obsidian memory files to reflect what changed
8. **Commit** — **user does this manually** after reviewing memory + tests

For bugs: steps 1 → `systematic-debugging` → TDD → 5 → 6 → 7 → 8.

**Boot protocol for every aria session:** Read `aria/memory/MEMORY.md` first, then the three linked memory files before touching any code.

---

**Commit workflow (CRITICAL — established 2026-05-27):**
- Claude does NOT commit during implementation or after code review
- Write code + tests → confirm tests pass → tell user → user commits manually
- After user commits: brain-save to update Obsidian memory with final state
- This is a hard rule: `git commit`, `git push`, `npm run deploy-*` are user-only operations

---

## Mandatory: All Docs/Specs/Plans → Obsidian Vault

- Every superpowers spec written to `docs/superpowers/specs/` must ALSO be written to the Obsidian vault at `aria/docs/specs/YYYY-MM-DD-<topic>-design.md` and cross-linked from `[[NEXT]]` or the relevant flow note.
- Every superpowers plan written to `docs/superpowers/plans/` must ALSO be written to `aria/docs/plans/YYYY-MM-DD-<topic>-plan.md` and linked from `[[NEXT]]`.
- Run `brain-search` before writing any plan or spec to gather current project context.
- The `docs/` folder in the codebase is being deprecated — all documentation lives in the Obsidian vault going forward.

---

## sheet_synchonizer is credentials-only — no side effects

`GoogleSheetSynchonizer.grab_accounts()` only upserts `profile`, `login`, `password`, `proxy`. The new `sync_single_account(profile)` method is the only exception — it's called explicitly when an account enters `pending_release` to capture final points before ownership ends.

**Why:** check_all was a hidden side effect inside a sync operation. Progress checks are now triggered explicitly.
