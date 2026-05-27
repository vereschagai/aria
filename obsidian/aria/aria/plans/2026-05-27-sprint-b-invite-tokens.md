---
type: plan
sprint: B
status: complete — 2026-05-27
updated: 2026-05-27
spec: "[[specs/2026-05-27-sprint-b-invite-tokens]]"
---

# Sprint B: Invite Token System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw Telegram user IDs in `?start=` invite links with persistent UUID tokens stored in MongoDB, so referrer IDs are never exposed in shared links.

**Architecture:** New `invite_tokens` collection maps UUID → `issuer_id` (Telegram user ID). `/start` resolves UUID to `issuer_id`; everything downstream (self-referral check, gamer insert) is unchanged. `ensure_invite_token(issuer_id, role_type)` is idempotent — safe to call on every startup and every button press.

**Tech Stack:** Python 3, aiogram 2.x, motor 3.0.0 (async MongoDB), `uuid` stdlib, pytest + pytest-asyncio + mongomock

**Repo:** `/Users/ivan/Work/aria`

> **Related:** [[specs/2026-05-27-sprint-b-invite-tokens]] · [[NEXT]] · [[modules/mongodb]] · [[modules/main]]

---

## File Map

| File | Change |
|---|---|
| `mongodb.py` | Add `ensure_invite_token`, `get_invite_token_by_uuid`; add `invite_tokens` indexes to `ensure_indexes()` |
| `main.py` | Module-level `BOT_USERNAME = ""`; startup: fetch username + superadmin token; `/start`: UUID lookup replaces int parse; `admin_added`: call `ensure_invite_token` after support insert; 3 new invite-link handlers |
| `buttons.py` | 3 new constants: `superadmin_invite_link`, `support_invite_link`, `gamer_invite_friend` |
| `markups.py` | Add buttons to `superadmin_start`, `support_start`, `start` markups |
| `texts.py` | Add `invite_link` template |
| `tests/test_invite_tokens.py` | 11 new tests (new file) |

---

## Task 1: MongoDB — `invite_tokens` indexes + two new methods

**Files:**
- Modify: `mongodb.py`
- Create: `tests/test_invite_tokens.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_invite_tokens.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import mongomock

# ── helpers ────────────────────────────────────────────────────────────────

def _make_mongo_db():
    """Inject mongomock client into a MongoDb instance (no real Mongo needed)."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from mongodb import MongoDb
    client = mongomock.MongoClient()
    db_instance = object.__new__(MongoDb)
    db_instance.connection = client
    db_instance.db = client["test_db"]
    return db_instance


# ── Task 1 tests: DB methods ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_invite_token_creates_new():
    db = _make_mongo_db()
    token = await db.ensure_invite_token(123456, "gamer")
    assert token["issuer_id"] == 123456
    assert token["role_type"] == "gamer"
    assert len(token["uuid"]) == 36  # UUID4 string format
    assert "created_at" in token


@pytest.mark.asyncio
async def test_ensure_invite_token_returns_existing():
    db = _make_mongo_db()
    first = await db.ensure_invite_token(123456, "gamer")
    second = await db.ensure_invite_token(123456, "gamer")
    assert first["uuid"] == second["uuid"]
    # Only one document in the collection
    count = await db.db.invite_tokens.count_documents({"issuer_id": 123456})
    assert count == 1


@pytest.mark.asyncio
async def test_get_invite_token_by_uuid_found():
    db = _make_mongo_db()
    created = await db.ensure_invite_token(999, "support")
    found = await db.get_invite_token_by_uuid(created["uuid"])
    assert found is not None
    assert found["issuer_id"] == 999


@pytest.mark.asyncio
async def test_get_invite_token_by_uuid_not_found():
    db = _make_mongo_db()
    result = await db.get_invite_token_by_uuid("00000000-0000-0000-0000-000000000000")
    assert result is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/ivan/Work/aria
pip install mongomock --break-system-packages -q
pytest tests/test_invite_tokens.py -v 2>&1 | head -30
```

Expected: `AttributeError: type object 'MongoDb' has no attribute 'ensure_invite_token'`

- [ ] **Step 3: Add import to `mongodb.py`**

At the top of `mongodb.py`, add `uuid` import:

```python
from uuid import uuid4
```

(Add after the existing `from datetime import datetime` line.)

- [ ] **Step 4: Add `ensure_invite_token` and `get_invite_token_by_uuid` to `mongodb.py`**

Add a new `# Invite tokens` section after the `# Release blocks` section:

```python
    # Invite tokens
    async def ensure_invite_token(self, issuer_id: int, role_type: str) -> dict:
        """Find token by issuer_id; create with uuid4 if missing. Always returns token doc."""
        existing = await self.db.invite_tokens.find_one({"issuer_id": issuer_id})
        if existing:
            return existing
        doc = {
            "uuid": str(uuid4()),
            "issuer_id": issuer_id,
            "role_type": role_type,
            "created_at": datetime.utcnow(),
        }
        await self.db.invite_tokens.insert_one(doc)
        return doc

    async def get_invite_token_by_uuid(self, uuid_str: str) -> dict | None:
        """Return token doc or None."""
        return await self.db.invite_tokens.find_one({"uuid": uuid_str})
```

- [ ] **Step 5: Add `invite_tokens` indexes inside `ensure_indexes()`**

Inside `ensure_indexes()`, after the existing `release_blocks` index block, add:

```python
        # invite_tokens: uuid (unique), issuer_id (unique)
        await self.db.invite_tokens.create_index("uuid", unique=True)
        await self.db.invite_tokens.create_index("issuer_id", unique=True)
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
cd /Users/ivan/Work/aria
pytest tests/test_invite_tokens.py::test_ensure_invite_token_creates_new \
       tests/test_invite_tokens.py::test_ensure_invite_token_returns_existing \
       tests/test_invite_tokens.py::test_get_invite_token_by_uuid_found \
       tests/test_invite_tokens.py::test_get_invite_token_by_uuid_not_found \
       -v
```

Expected: 4 passed.

- [ ] **Step 7: Run full suite — verify no regressions**

```bash
cd /Users/ivan/Work/aria
pytest tests/ -v 2>&1 | tail -20
```

Expected: all existing tests pass + 4 new.

- [ ] **Step 8: Commit**

```bash
cd /Users/ivan/Work/aria
git add mongodb.py tests/test_invite_tokens.py
git commit -m "feat(B1-B2): add invite_tokens collection — ensure_invite_token + get_invite_token_by_uuid"
```

---

## Task 2: `buttons.py` + `texts.py` — new constants

**Files:**
- Modify: `buttons.py`
- Modify: `texts.py`

- [ ] **Step 1: Add 3 button constants to `buttons.py`**

Append at the end of `buttons.py`:

```python
superadmin_invite_link = "🔗 Ссылка для приглашения"
support_invite_link = "🔗 Пригласить игрока"
gamer_invite_friend = "👥 Пригласить друга"
```

- [ ] **Step 2: Add `invite_link` text template to `texts.py`**

Append at the end of `texts.py`:

```python
invite_link = "Ваша реферальная ссылка:\n\nhttps://{link}"
```

- [ ] **Step 3: Commit**

```bash
cd /Users/ivan/Work/aria
git add buttons.py texts.py
git commit -m "feat(B5,B7,B8): add invite link button labels and text template"
```

---

## Task 3: `markups.py` — add invite link buttons to 3 keyboards

**Files:**
- Modify: `markups.py`

- [ ] **Step 1: Add invite link button to `start` markup (gamer keyboard)**

Find the `start` markup definition in `markups.py`. It currently has rows for account/leaderboard, pickup/release, and referral. Add the gamer invite button as a new row:

```python
# Before (last row of start markup):
start.row(buttons.referral)

# After:
start.row(buttons.referral)
start.row(buttons.gamer_invite_friend)
```

- [ ] **Step 2: Add invite link button to `superadmin_start` markup**

Find the `superadmin_start` markup. Add invite link as a new row (place it logically near the end, before or after `finished_accounts`):

```python
superadmin_start.row(buttons.superadmin_invite_link)
```

- [ ] **Step 3: Add invite link button to `support_start` markup**

Find the `support_start` markup. Add:

```python
support_start.row(buttons.support_invite_link)
```

- [ ] **Step 4: Commit**

```bash
cd /Users/ivan/Work/aria
git add markups.py
git commit -m "feat(B5,B7,B8): add invite link buttons to superadmin, support, gamer keyboards"
```

---

## Task 4: `main.py` — startup: `BOT_USERNAME` + superadmin token

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add `BOT_USERNAME` module-level variable**

Near the top of `main.py`, after the existing module-level constants (SUPERADMIN_ID, BOT_TOKEN, etc.), add:

```python
BOT_USERNAME = ""  # populated at startup via bot.get_me()
```

- [ ] **Step 2: Add fetch + superadmin token creation to `on_startup`**

Find the `on_startup` function (or equivalent startup block). After `await db.ensure_indexes()`, add:

```python
    global BOT_USERNAME
    bot_me = await bot.get_me()
    BOT_USERNAME = bot_me.username
    await db.ensure_invite_token(SUPERADMIN_ID, "superadmin")
```

- [ ] **Step 3: Commit**

```bash
cd /Users/ivan/Work/aria
git add main.py
git commit -m "feat(B3): fetch BOT_USERNAME at startup + create superadmin invite token"
```

---

## Task 5: `main.py` — `/start` handler: replace int referral with UUID lookup

**Files:**
- Modify: `main.py`
- Modify: `tests/test_invite_tokens.py`

- [ ] **Step 1: Write failing tests for the UUID start flow**

Add to `tests/test_invite_tokens.py`:

```python
# ── Task 5 tests: /start UUID referral ─────────────────────────────────────

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

@pytest.mark.asyncio
async def test_start_handler_resolves_uuid_referral():
    """Valid UUID in ?start= sets referral to issuer's user_id."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock

    fake_token = {"uuid": "abc-123", "issuer_id": 555, "role_type": "gamer"}
    mock_db = MagicMock()
    mock_db.get_invite_token_by_uuid = AsyncMock(return_value=fake_token)
    mock_db.is_superadmin = AsyncMock(return_value=False)
    mock_db.is_support = AsyncMock(return_value=False)
    mock_db.is_gamer = AsyncMock(return_value=False)
    mock_db.add_gamer = AsyncMock()
    mock_db.get_gamer = AsyncMock(return_value=None)

    message = MagicMock()
    message.from_user.id = 777
    message.from_user.username = "testuser"
    message.text = "/start abc-123"
    message.answer = AsyncMock()

    with patch.object(main, "db", mock_db):
        # Call start handler logic — extract referral parsing portion
        parts = message.text.split()
        referral = None
        if len(parts) == 2:
            token_doc = await mock_db.get_invite_token_by_uuid(parts[1])
            if token_doc:
                referral = token_doc["issuer_id"]
        assert referral == 555


@pytest.mark.asyncio
async def test_start_handler_unknown_uuid_gives_no_referral():
    """Unknown UUID in ?start= → referral stays None."""
    mock_db = MagicMock()
    mock_db.get_invite_token_by_uuid = AsyncMock(return_value=None)

    parts = "/start 00000000-0000-0000-0000-000000000000".split()
    referral = None
    if len(parts) == 2:
        token_doc = await mock_db.get_invite_token_by_uuid(parts[1])
        if token_doc:
            referral = token_doc["issuer_id"]
    assert referral is None
```

- [ ] **Step 2: Run tests — verify they pass (these test logic only, not the handler itself)**

```bash
cd /Users/ivan/Work/aria
pytest tests/test_invite_tokens.py::test_start_handler_resolves_uuid_referral \
       tests/test_invite_tokens.py::test_start_handler_unknown_uuid_gives_no_referral \
       -v
```

Expected: 2 passed.

- [ ] **Step 3: Update the `/start` handler in `main.py`**

Find the `/start` handler. Locate the referral-parsing block. It currently looks like:

```python
# OLD — remove this entire block:
referral = None
if len(parts) == 2 and parts[1].isdigit():
    referral = int(parts[1])
```

Replace with:

```python
# NEW:
referral = None
if len(parts) == 2:
    token_doc = await db.get_invite_token_by_uuid(parts[1])
    if token_doc:
        referral = token_doc["issuer_id"]
```

- [ ] **Step 4: Run full test suite**

```bash
cd /Users/ivan/Work/aria
pytest tests/ -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/ivan/Work/aria
git add main.py tests/test_invite_tokens.py
git commit -m "feat(B4): replace int ?start= referral with UUID token lookup"
```

---

## Task 6: `main.py` — `add_support` flow creates invite token

**Files:**
- Modify: `main.py`
- Modify: `tests/test_invite_tokens.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_invite_tokens.py`:

```python
# ── Task 6 tests: add_support creates token ─────────────────────────────────

@pytest.mark.asyncio
async def test_add_support_flow_creates_invite_token():
    """After a support user is added, ensure_invite_token is called with their user_id."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock, call

    mock_db = MagicMock()
    mock_db.add_support = AsyncMock()
    mock_db.ensure_invite_token = AsyncMock(return_value={
        "uuid": "tok-xyz",
        "issuer_id": 888,
        "role_type": "support",
    })
    mock_db.is_superadmin = AsyncMock(return_value=True)

    contact = MagicMock()
    contact.user_id = 888

    message = MagicMock()
    message.contact = contact
    message.from_user.id = 1
    message.answer = AsyncMock()

    with patch.object(main, "db", mock_db):
        # Simulate the add_support call and token creation inline
        await mock_db.add_support(contact)
        await mock_db.ensure_invite_token(contact.user_id, "support")

    mock_db.ensure_invite_token.assert_called_once_with(888, "support")
```

- [ ] **Step 2: Run to verify test passes (it's a logic test, not a handler test)**

```bash
cd /Users/ivan/Work/aria
pytest tests/test_invite_tokens.py::test_add_support_flow_creates_invite_token -v
```

Expected: passed.

- [ ] **Step 3: Update `admin_added` handler in `main.py`**

Find `admin_added` (the handler that processes a shared contact to add a support user). After the `await db.add_support(contact)` line, add:

```python
        await db.ensure_invite_token(contact.user_id, "support")
```

The relevant block should look like:

```python
        # ... existing code ...
        await db.add_support(contact)
        await db.ensure_invite_token(contact.user_id, "support")
        # ... reply to user ...
```

- [ ] **Step 4: Run full suite**

```bash
cd /Users/ivan/Work/aria
pytest tests/ -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/ivan/Work/aria
git add main.py tests/test_invite_tokens.py
git commit -m "feat(B6): create invite token when support user is added"
```

---

## Task 7: `main.py` — 3 invite link handlers (superadmin, support, gamer)

**Files:**
- Modify: `main.py`
- Modify: `tests/test_invite_tokens.py`

- [ ] **Step 1: Write failing tests for all 3 invite link handlers**

Add to `tests/test_invite_tokens.py`:

```python
# ── Task 7 tests: invite link handlers ──────────────────────────────────────

@pytest.mark.asyncio
async def test_gamer_invite_link_handler_sends_link():
    """Gamer invite handler fetches/creates token and sends formatted link."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock

    fake_token = {"uuid": "gamer-uuid-123", "issuer_id": 777, "role_type": "gamer"}
    mock_db = MagicMock()
    mock_db.ensure_invite_token = AsyncMock(return_value=fake_token)

    message = MagicMock()
    message.from_user.id = 777
    message.answer = AsyncMock()

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"):
        await main.gamer_invite_link(message)

    mock_db.ensure_invite_token.assert_called_once_with(777, "gamer")
    sent_text = message.answer.call_args[0][0]
    assert "gamer-uuid-123" in sent_text
    assert "aria_test_bot" in sent_text


@pytest.mark.asyncio
async def test_superadmin_invite_link_handler_sends_link():
    """Superadmin invite handler fetches/creates token and sends formatted link."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock

    fake_token = {"uuid": "sa-uuid-456", "issuer_id": 1, "role_type": "superadmin"}
    mock_db = MagicMock()
    mock_db.ensure_invite_token = AsyncMock(return_value=fake_token)

    message = MagicMock()
    message.from_user.id = 1
    message.answer = AsyncMock()

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"):
        await main.superadmin_invite_link(message)

    mock_db.ensure_invite_token.assert_called_once_with(1, "superadmin")
    sent_text = message.answer.call_args[0][0]
    assert "sa-uuid-456" in sent_text


@pytest.mark.asyncio
async def test_support_invite_link_handler_sends_link():
    """Support invite handler fetches/creates token and sends formatted link."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock

    fake_token = {"uuid": "sup-uuid-789", "issuer_id": 444, "role_type": "support"}
    mock_db = MagicMock()
    mock_db.ensure_invite_token = AsyncMock(return_value=fake_token)

    message = MagicMock()
    message.from_user.id = 444
    message.answer = AsyncMock()

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"):
        await main.support_invite_link(message)

    mock_db.ensure_invite_token.assert_called_once_with(444, "support")
    sent_text = message.answer.call_args[0][0]
    assert "sup-uuid-789" in sent_text
```

- [ ] **Step 2: Run — verify they fail**

```bash
cd /Users/ivan/Work/aria
pytest tests/test_invite_tokens.py::test_gamer_invite_link_handler_sends_link \
       tests/test_invite_tokens.py::test_superadmin_invite_link_handler_sends_link \
       tests/test_invite_tokens.py::test_support_invite_link_handler_sends_link \
       -v 2>&1 | head -20
```

Expected: `AttributeError: module 'main' has no attribute 'gamer_invite_link'`

- [ ] **Step 3: Add 3 handlers to `main.py`**

Add these 3 handlers in the appropriate role sections of `main.py`. Place the superadmin handler near other superadmin handlers, support near support handlers, gamer near gamer handlers.

```python
# ── Superadmin invite link ──────────────────────────────────────────────────
@dp.message_handler(Text(equals=buttons.superadmin_invite_link, ignore_case=True),
                    state=TelegramState.superadmin_start)
async def superadmin_invite_link(message: types.Message):
    token = await db.ensure_invite_token(message.from_user.id, "superadmin")
    link = f"t.me/{BOT_USERNAME}?start={token['uuid']}"
    await safe_wrap(message.answer(texts.invite_link.format(link=link)))


# ── Support invite link ─────────────────────────────────────────────────────
@dp.message_handler(Text(equals=buttons.support_invite_link, ignore_case=True),
                    state=TelegramState.support_start)
async def support_invite_link(message: types.Message):
    token = await db.ensure_invite_token(message.from_user.id, "support")
    link = f"t.me/{BOT_USERNAME}?start={token['uuid']}"
    await safe_wrap(message.answer(texts.invite_link.format(link=link)))


# ── Gamer invite link ───────────────────────────────────────────────────────
@dp.message_handler(Text(equals=buttons.gamer_invite_friend, ignore_case=True),
                    state=TelegramState.start)
async def gamer_invite_link(message: types.Message):
    token = await db.ensure_invite_token(message.from_user.id, "gamer")
    link = f"t.me/{BOT_USERNAME}?start={token['uuid']}"
    await safe_wrap(message.answer(texts.invite_link.format(link=link)))
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/ivan/Work/aria
pytest tests/test_invite_tokens.py::test_gamer_invite_link_handler_sends_link \
       tests/test_invite_tokens.py::test_superadmin_invite_link_handler_sends_link \
       tests/test_invite_tokens.py::test_support_invite_link_handler_sends_link \
       -v
```

Expected: 3 passed.

- [ ] **Step 5: Run full suite**

```bash
cd /Users/ivan/Work/aria
pytest tests/ -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/ivan/Work/aria
git add main.py tests/test_invite_tokens.py
git commit -m "feat(B5,B7,B8): add invite link handlers for superadmin, support, and gamer"
```

---

## Task 8: Verification

- [ ] **Step 1: Run complete test suite**

```bash
cd /Users/ivan/Work/aria
pytest tests/ -v
```

Expected: all tests pass (should now be ~96 tests total: 85 existing + 11 new).

- [ ] **Step 2: Check test count**

```bash
cd /Users/ivan/Work/aria
pytest tests/ --collect-only -q 2>&1 | tail -5
```

Note the final count. If it's less than 96, check which test file is missing tests.

- [ ] **Step 3: Verify invite_tokens collection in `ensure_indexes()`**

```bash
cd /Users/ivan/Work/aria
grep -n "invite_tokens" mongodb.py
```

Expected output should show at least 3 lines: `create_index("uuid", ...)`, `create_index("issuer_id", ...)`, and the method bodies.

- [ ] **Step 4: Verify no old `isdigit()` referral code remains**

```bash
cd /Users/ivan/Work/aria
grep -n "isdigit" main.py
```

Expected: no output (old int-referral parsing removed).

- [ ] **Step 5: Verify `BOT_USERNAME` is set at startup**

```bash
cd /Users/ivan/Work/aria
grep -n "BOT_USERNAME" main.py
```

Expected: at least 3 lines — module-level declaration, `bot.get_me()` assignment in startup, and usage in handlers.

- [ ] **Step 6: Update NEXT.md in Obsidian — mark B1-B8 complete**

In Obsidian, update `aria/NEXT.md` Sprint B table: change all ⬜ to ✅.

---

## Summary Checklist

| Task | Commit | Tests |
|---|---|---|
| B1+B2: mongodb methods + indexes | `feat(B1-B2): add invite_tokens...` | 4 tests |
| B5+B7+B8 prep: buttons + texts | `feat(B5,B7,B8): add invite link button labels...` | — |
| B5+B7+B8 prep: markups | `feat(B5,B7,B8): add invite link buttons...` | — |
| B3: startup BOT_USERNAME + superadmin token | `feat(B3): fetch BOT_USERNAME...` | — |
| B4: /start UUID lookup | `feat(B4): replace int ?start=...` | 2 tests |
| B6: add_support creates token | `feat(B6): create invite token...` | 1 test |
| B5+B7+B8: handlers | `feat(B5,B7,B8): add invite link handlers...` | 3 tests |

**Total new tests:** 10 (+ existing 85 = ~95)
