---
name: feedback-aria-workflow
description: Workflow rules for the Aria project — what Claude does vs. what the
  user does, and key coding patterns to always follow
type: feedback
updated: 2026-05-26
version: "3"
---

# Aria Project — Workflow & Coding Rules

See [[memory/project_aria|Project Overview]] for architecture context.

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

**Why:** Telegram API returns transient 429/5xx errors. Direct calls crash on rate limits.

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

**How to apply:** Every screen transition — no exceptions.

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

**Why:** Unescaped `_`, `*`, `[`, `.`, etc. crash MarkdownV2 rendering.

**How to apply:** All user-sourced strings (usernames, profile names, wallet addresses) in MarkdownV2 templates. Static strings in `texts.py` are pre-escaped. See [[modules/texts]], [[modules/utils]].

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

---

## Obsidian vault is the knowledge base of record

After any non-trivial implementation:
1. Update `CLAUDE.md` and relevant `docs/` file
2. Update vault: [[CONTEXT]], [[PROGRESS]], [[DECISIONS]] (new ADR if applicable)
3. Update affected [[modules/]] or [[flows/]] notes
4. Run brain-save to update session handoff in [[memory/MEMORY]]

**Why:** Documented in global CLAUDE.md as mandatory workflow step. Without this, next session starts blind.

---

## Mandatory Cowork implementation workflow

Every non-trivial task must follow this sequence (from Cowork system prompt):

1. **brain-search** — search `aria/memory/` via Obsidian MCP before starting any work
2. **System design** — use `engineering:system-design` skill for features; skip for simple bugs
3. **Implement** changes
4. **Dry-test** — run `pytest tests/ -v` or equivalent check
5. **Code review** — use `engineering:code-review` skill
6. **Fix vault docs** — update Obsidian memory files to reflect what changed
7. **Commit** all reviewed changes + vault update (user does the push/deploy)

Use Engineering plugin skills: `engineering:code-review`, `engineering:system-design`, `engineering:testing-strategy`, `engineering:documentation` as appropriate.

**Boot protocol for every aria session:** Read `aria/memory/MEMORY.md` first, then the three linked memory files before touching any code.

---

## sheet_synchonizer is credentials-only — no side effects

`GoogleSheetSynchonizer.grab_accounts()` only upserts `profile`, `login`, `password`, `proxy`. It does **not** call `progress_monitor.check_all()` or trigger any downstream logic. The `progress_monitor` parameter was removed entirely.

**Why:** check_all was a hidden side effect inside a sync operation, making the flow hard to reason about. Progress checks are now triggered explicitly elsewhere.
