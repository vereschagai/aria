---
type: spec
sprint: B
status: complete — 2026-05-27
updated: 2026-05-27
---

# Sprint B — Invite Token System Design

> **Related:** [[NEXT]] · [[flows/start-role-resolution]] · [[modules/mongodb]] · [[modules/main]] · [[modules/buttons]] · [[modules/texts]] · [[modules/markups]] · [[memory/project_aria]]

## Goal

Replace raw Telegram user IDs in `?start=` invite links with persistent UUID tokens. Security improvement: referrer's Telegram ID is no longer exposed in shared links. Everyone who joins via any invite link still registers as a **gamer** — the token is a pure lookup layer with no effect on role assignment.

---

## Option chosen: UUID as pure lookup layer (Option A)

`invite_tokens` collection maps UUID → Telegram user ID. On `/start`, UUID is resolved to the issuer's Telegram ID, then the existing referral validation runs unchanged. `gamer.referral` still stores the referrer's Telegram user ID as an `int` — nothing downstream changes.

Alternatives considered and rejected:
- **Option B** (UUID replaces `gamer.referral`): invasive, requires changing account screen + referral count display
- **Option C** (store both UUID and resolved ID): YAGNI — no analytics need yet

---

## Data Model

New collection: `invite_tokens`

```
{
  _id: ObjectId,
  uuid: str,         # unique index — used as ?start= payload
  issuer_id: int,    # unique index — Telegram user ID of token owner
  role_type: "superadmin" | "support" | "gamer",
  created_at: datetime
}
```

Two indexes: `uuid` unique (for lookup), `issuer_id` unique (so upsert is safe).

**Tokens are permanent for the season — no rotation or revocation.**

---

## New `mongodb.py` Methods

```python
async def ensure_invite_token(self, issuer_id: int, role_type: str) -> dict:
    """Find token by issuer_id; create with uuid4 if missing. Always returns token doc."""

async def get_invite_token_by_uuid(self, uuid_str: str) -> dict | None:
    """Return token doc or None."""
```

Also: `ensure_indexes()` gets two new entries for `invite_tokens`.

---

## Token Lifecycle

| Who | When created | How |
|---|---|---|
| Superadmin | Bot startup | `ensure_invite_token(SUPERADMIN_ID, "superadmin")` in startup block |
| Support | When added via `add_support` flow | `ensure_invite_token(contact.user_id, "support")` after support insert |
| Gamer | Lazily on demand | Created when gamer presses "👥 Пригласить друга" button |

All three use the same `ensure_invite_token` — idempotent, safe to call repeatedly.

---

## `/start` Handler Changes

**Remove** the `parts[1].isdigit()` branch entirely (backwards compatibility with old int links: **none — clean cut**).

**New logic:**
```python
referral = None
if len(parts) == 2:
    token_doc = await db.get_invite_token_by_uuid(parts[1])
    if token_doc:
        referral = token_doc["issuer_id"]  # int — same type as before
# If UUID not found → referral stays None → join blocked (invite-only system)
```

Everything downstream is **unchanged**: self-referral check, superadmin/support/gamer validation, FSM defer for no-username case, `gamer.referral` storage.

---

## Bot Username

Needed to construct `t.me/<bot>?start=<uuid>` links. Fetch once at startup:
```python
bot_me = await bot.get_me()
BOT_USERNAME = bot_me.username  # module-level variable
```

---

## UI — Three New Buttons

All three handlers call `ensure_invite_token(user_id, role_type)` then send the link as a plain text message (not MarkdownV2 — link must be copyable as plain text).

| Role | Button label | FSM state |
|---|---|---|
| Superadmin | "🔗 Ссылка для приглашения" | `TelegramState.superadmin_start` |
| Support | "🔗 Пригласить игрока" | `TelegramState.support_start` |
| Gamer | "👥 Пригласить друга" | `TelegramState.start` |

Handler logic (identical for all three):
```python
token = await db.ensure_invite_token(message.from_user.id, role_type)
link = f"t.me/{BOT_USERNAME}?start={token['uuid']}"
await message.answer(texts.invite_link.format(link=link))
```

---

## Roles Clarification

`role_type` on the token is attribution metadata only — shown as "Админ" on the gamer's account screen if referrer is superadmin or support (existing display logic unchanged). Anyone joining via any token type registers as a gamer.

Support users are added via a separate flow (`add_support` — contact sharing), never via invite links.

---

## Files Changed

| File | Changes |
|---|---|
| `mongodb.py` | `ensure_indexes()` + `ensure_invite_token` + `get_invite_token_by_uuid` |
| `main.py` | Startup block (`BOT_USERNAME`, superadmin token); `/start` handler (UUID lookup); 3 new invite link handlers |
| `buttons.py` | 3 new button label constants |
| `markups.py` | Add buttons to `superadmin_start`, `support_start`, `start` markups |
| `texts.py` | `invite_link` template |

---

## Out of Scope

- Token rotation or revocation
- Support user registration via invite link
- Backwards compatibility with old `?start=<int>` links — clean cut, old links stop working
- Analytics on which token was used to join

---

## Implementation Plan

→ See `docs/superpowers/plans/` for the step-by-step implementation plan (written after spec approval).

See [[NEXT#Sprint B — Invite Token System]] for task breakdown (B1–B8).
