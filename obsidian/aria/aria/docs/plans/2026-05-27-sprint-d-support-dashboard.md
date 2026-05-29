# Sprint D: Support Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a paginated "📋 Задачи" dashboard for support (action buttons) and superadmin (read-only DM buttons) showing all open escalations and release requests in one inline-keyboard message, plus DM buttons on all support notifications.

**Architecture:** New `get_open_support_tasks()` DB method returns accounts with status `escalated` or `pending_release` with gamer info joined. A pure `_build_dashboard_page()` helper in `main.py` renders the paginated message text + `InlineKeyboardMarkup`. A `dash_page:{n}` callback edits the existing dashboard message in-place. Existing `release_pool/finish/deny` callbacks (registered `state="*"`) handle actions from the dashboard without changes. DM URL buttons (`tg://user?id={id}`) added to escalation and release request notifications.

**Tech Stack:** aiogram 2.x, Motor async MongoDB, pytest + pytest-asyncio + mongomock. No new dependencies.

**Status:** ✅ Implemented (Sprint D, 2026-05-27)

---

## Files Modified / Created

| File | Change |
|---|---|
| `mongodb.py` | Add `get_open_support_tasks()` |
| `state.py` | Add `support_dashboard` FSM state |
| `buttons.py` | Add `support_tasks = "📋 Задачи"` |
| `markups.py` | Add `support_tasks` button to `support_start` and `superadmin_start` |
| `texts.py` | Add `support_dashboard_empty` |
| `main.py` | Add `PAGE_SIZE`, `_build_dashboard_page()`, dashboard handler, `dash_page` callback, `dash_noop` callback, back-navigation for `support_dashboard` state; add DM button to release request notification |
| `progress_monitor.py` | Add DM URL button to `_escalate()` markup |
| `tests/test_sprint_d.py` | New test file (created) |

---

## Task 1: DB — `get_open_support_tasks()`

**Files:**
- Modify: `mongodb.py`
- Test: `tests/test_sprint_d.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_sprint_d.py`:

```python
"""Sprint D — Support Dashboard tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId


# ---------------------------------------------------------------------------
# Helpers shared across tasks
# ---------------------------------------------------------------------------

class _AsyncCollection:
    def __init__(self, col):
        self._col = col
    async def find_one(self, *a, **kw):
        return self._col.find_one(*a, **kw)
    async def insert_one(self, *a, **kw):
        return self._col.insert_one(*a, **kw)
    async def find(self, *a, **kw):
        return self._col.find(*a, **kw)
    async def count_documents(self, *a, **kw):
        return self._col.count_documents(*a, **kw)
    async def create_index(self, *a, **kw):
        return self._col.create_index(*a, **kw)
    async def update_one(self, *a, **kw):
        return self._col.update_one(*a, **kw)
    def to_list(self, n):
        # wrap synchronous cursor as awaitable list
        import asyncio
        results = list(self._col)
        future = asyncio.get_event_loop().create_future()
        future.set_result(results)
        return future


class _AsyncDb:
    def __init__(self, db):
        self._db = db
    def __getattr__(self, name):
        return _AsyncCollection(self._db[name])


def _make_mongo_db():
    import sys, os, mongomock
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from mongodb import MongoDb
    client = mongomock.MongoClient()
    instance = object.__new__(MongoDb)
    instance.connection = client
    instance.db = _AsyncDb(client["test_db"])
    return instance


# ---------------------------------------------------------------------------
# Task 1: get_open_support_tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_open_support_tasks_returns_only_open():
    """Only escalated and pending_release accounts are returned; active/released are excluded."""
    import mongomock
    from bson import ObjectId
    from datetime import datetime

    db = _make_mongo_db()
    gamer_oid = ObjectId()

    # Insert accounts
    db.db._db["accounts"].insert_many([
        {"profile": "acc_escalated", "status": "escalated",       "gamer_id": gamer_oid},
        {"profile": "acc_pending",   "status": "pending_release",  "gamer_id": gamer_oid},
        {"profile": "acc_active",    "status": "active",           "gamer_id": gamer_oid},
        {"profile": "acc_released",  "status": "released",         "gamer_id": None},
    ])
    db.db._db["gamers"].insert_one({"_id": gamer_oid, "id": 111, "username": "player1"})

    tasks = await db.get_open_support_tasks()

    profiles = [t["profile"] for t in tasks]
    assert "acc_escalated" in profiles
    assert "acc_pending" in profiles
    assert "acc_active" not in profiles
    assert "acc_released" not in profiles
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /path/to/aria && pytest tests/test_sprint_d.py::test_get_open_support_tasks_returns_only_open -v
```
Expected: `AttributeError: 'MongoDb' object has no attribute 'get_open_support_tasks'`

- [ ] **Step 3: Implement `get_open_support_tasks()` in `mongodb.py`**

Add after `get_escalated_accounts()` (around line 193):

```python
async def get_open_support_tasks(self) -> list:
    """
    All accounts awaiting support action (escalated + pending_release),
    with gamer info joined. Escalated accounts come before pending_release.
    Each item has a 'gamer' key (joined gamer doc, or None if no gamer_id).
    """
    accounts = await self.db.accounts.find(
        {"status": {"$in": ["escalated", "pending_release"]}}
    ).to_list(None)

    result = []
    for account in accounts:
        gamer = None
        gamer_id = account.get("gamer_id")
        if gamer_id:
            gamer = await self.db.gamers.find_one({"_id": gamer_id})
        result.append({**account, "gamer": gamer})

    # Escalated first, then pending_release
    result.sort(key=lambda a: 0 if a["status"] == "escalated" else 1)
    return result
```

---

## Task 2: State, Buttons, Markup, Texts

**Files:**
- Modify: `state.py`, `buttons.py`, `markups.py`, `texts.py`

- [ ] **Step 1: Add `support_dashboard` state to `state.py`**

```python
# After support_remove_confirm:
support_dashboard = State()
```

- [ ] **Step 2: Add `support_tasks` button label to `buttons.py`**

```python
support_tasks = "📋 Задачи"
```

- [ ] **Step 3: Add button to markups in `markups.py`**

```python
# support_start: add support_tasks row after finished_accounts
support_start.add(buttons.support_tasks)

# superadmin_start: add support_tasks row after finished_accounts
superadmin_start.add(buttons.support_tasks)
```

- [ ] **Step 4: Add `support_dashboard_empty` text to `texts.py`**

```python
support_dashboard_empty = '''
📋 *Нет открытых задач\.* Всё спокойно\!
'''
```

---

## Task 3: Dashboard Handler + Pagination Callback

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add `PAGE_SIZE` and `_build_dashboard_page()` to `main.py`**

```python
PAGE_SIZE = 5

async def _build_dashboard_page(tasks: list, page: int, viewer_is_superadmin: bool):
    total = len(tasks)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_tasks = tasks[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    lines = [f"📋 *Открытые задачи* — стр\\. {page + 1}/{total_pages}\n"]
    markup = types.InlineKeyboardMarkup(row_width=4)

    for local_i, task in enumerate(page_tasks):
        n = page * PAGE_SIZE + local_i + 1
        profile = utils.escape(task["profile"])
        gamer = task.get("gamer")
        username_str = utils.escape(f"@{gamer['username']}") if gamer and gamer.get("username") else "_неизвестен_"
        icon = "🚨" if task["status"] == "escalated" else "⏳"
        lines.append(f"{n}\\. {icon} `{profile}` — {username_str}")

        oid = str(task["_id"])
        gamer_tg_id = gamer.get("id") if gamer else None

        row = []
        if not viewer_is_superadmin:
            row.append(types.InlineKeyboardButton(f"{n} 🔓", callback_data=f"release_pool:{oid}"))
            row.append(types.InlineKeyboardButton(f"{n} 🚫", callback_data=f"release_finish:{oid}"))
            if task["status"] == "pending_release":
                row.append(types.InlineKeyboardButton(f"{n} ↩️", callback_data=f"release_deny:{oid}"))
        if gamer_tg_id:
            row.append(types.InlineKeyboardButton("💬 DM", url=f"tg://user?id={gamer_tg_id}"))
        if row:
            markup.add(*row)

    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("◀️", callback_data=f"dash_page:{page - 1}"))
    nav.append(types.InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="dash_noop"))
    if page < total_pages - 1:
        nav.append(types.InlineKeyboardButton("▶️", callback_data=f"dash_page:{page + 1}"))
    nav.append(types.InlineKeyboardButton("🔄", callback_data=f"dash_page:{page}"))
    markup.add(*nav)

    return "\n".join(lines), markup
```

---

## Task 4: DM Button in Escalation Notifications (`progress_monitor.py`)

- [ ] **Add DM button to `progress_monitor._escalate()`**

```python
if gamer_tg_id:
    markup.add(InlineKeyboardButton("💬 DM", url=f"tg://user?id={gamer_tg_id}"))
```

---

## Task 5: DM Button in Release Request Notification (`main.py`)

- [ ] **Add DM button to release request notification in `gamer_release_account_select`**

```python
gamer_tg_id_for_dm = gamer.get("id") if gamer else None
if gamer_tg_id_for_dm:
    support_markup.add(types.InlineKeyboardButton("💬 DM", url=f"tg://user?id={gamer_tg_id_for_dm}"))
```

---

## Self-Review Checklist

- D1 `get_open_support_tasks()` → Task 1 ✅
- D2 `support_dashboard` FSM state → Task 2 ✅
- D3 Dashboard message with pagination → Task 3 ✅
- D4 "📋 Задачи" on support home + superadmin home (read-only for SA) → Task 2 + Task 3 ✅
- D5 Existing `release_pool/finish/deny` callbacks work from dashboard (`state="*"`) → No code change needed ✅
- D6 DM button in `_escalate()` → Task 4 ✅
- D6 DM button in release request notification → Task 5 ✅
