"""Sprint D — Support Dashboard tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId


# ---------------------------------------------------------------------------
# TelegramState stub (same pattern as test_gamer_handlers.py)
# ---------------------------------------------------------------------------

class _AsyncState:
    """Stands in for any aiogram State object: .set() returns a real coroutine."""
    async def set(self):
        pass


class _TelegramStateMock:
    """Every attribute access returns a fresh _AsyncState."""
    def __getattr__(self, name):
        return _AsyncState()


def _ts():
    return _TelegramStateMock()


# ---------------------------------------------------------------------------
# Helpers shared across tasks
# ---------------------------------------------------------------------------

class _AsyncCursor:
    """Wraps a synchronous mongomock cursor so .to_list() is awaitable (matches Motor API)."""
    def __init__(self, cursor):
        self._cursor = cursor

    async def to_list(self, n):
        results = list(self._cursor)
        return results if n is None else results[:n]


class _AsyncCollection:
    def __init__(self, col):
        self._col = col

    async def find_one(self, *a, **kw):
        return self._col.find_one(*a, **kw)

    async def insert_one(self, *a, **kw):
        return self._col.insert_one(*a, **kw)

    def find(self, *a, **kw):
        # Sync, like Motor — returns cursor with async to_list
        return _AsyncCursor(self._col.find(*a, **kw))

    async def count_documents(self, *a, **kw):
        return self._col.count_documents(*a, **kw)

    async def create_index(self, *a, **kw):
        return self._col.create_index(*a, **kw)

    async def update_one(self, *a, **kw):
        return self._col.update_one(*a, **kw)

    def aggregate(self, pipeline):
        return _AsyncCursor(self._col.aggregate(pipeline))


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


@pytest.mark.asyncio
async def test_get_open_support_tasks_escalated_comes_first():
    """Escalated accounts are sorted before pending_release accounts."""
    import mongomock
    from bson import ObjectId

    db = _make_mongo_db()
    gamer_oid = ObjectId()
    db.db._db["accounts"].insert_many([
        {"profile": "p1", "status": "pending_release", "gamer_id": gamer_oid},
        {"profile": "p2", "status": "escalated",       "gamer_id": gamer_oid},
    ])
    db.db._db["gamers"].insert_one({"_id": gamer_oid, "id": 111, "username": "u"})

    tasks = await db.get_open_support_tasks()

    assert tasks[0]["status"] == "escalated"
    assert tasks[1]["status"] == "pending_release"


@pytest.mark.asyncio
async def test_get_open_support_tasks_joins_gamer():
    """Each task has a 'gamer' key with the joined gamer document."""
    import mongomock
    from bson import ObjectId

    db = _make_mongo_db()
    gamer_oid = ObjectId()
    db.db._db["accounts"].insert_one({"profile": "acc1", "status": "escalated", "gamer_id": gamer_oid})
    db.db._db["gamers"].insert_one({"_id": gamer_oid, "id": 555, "username": "testplayer"})

    tasks = await db.get_open_support_tasks()

    assert len(tasks) == 1
    assert tasks[0]["gamer"] is not None
    assert tasks[0]["gamer"]["username"] == "testplayer"
    assert tasks[0]["gamer"]["id"] == 555


@pytest.mark.asyncio
async def test_get_open_support_tasks_gamer_none_when_no_gamer_id():
    """Tasks with no gamer_id still appear; gamer key is None."""
    db = _make_mongo_db()
    db.db._db["accounts"].insert_one({"profile": "orphan", "status": "escalated", "gamer_id": None})

    tasks = await db.get_open_support_tasks()

    assert len(tasks) == 1
    assert tasks[0]["gamer"] is None


# ---------------------------------------------------------------------------
# Task 3: _build_dashboard_page helper
# ---------------------------------------------------------------------------

def _make_task(profile, status, gamer_id=None, gamer_tg_id=None, gamer_username=None):
    """Create a minimal task dict as returned by get_open_support_tasks()."""
    from bson import ObjectId
    gamer = None
    if gamer_tg_id is not None:
        gamer = {"id": gamer_tg_id, "username": gamer_username}
    return {
        "_id": ObjectId(),
        "profile": profile,
        "status": status,
        "gamer_id": gamer_id,
        "gamer": gamer,
    }


@pytest.mark.asyncio
async def test_build_dashboard_page_text_contains_profile():
    """Dashboard text includes the account profile name."""
    import main
    tasks = [_make_task("myprofile", "escalated", gamer_tg_id=111, gamer_username="player")]
    text, _ = await main._build_dashboard_page(tasks, page=0, viewer_is_superadmin=False)
    assert "myprofile" in text


@pytest.mark.asyncio
async def test_build_dashboard_page_support_has_action_buttons():
    """Support viewer gets release_pool, release_finish buttons."""
    import main
    tasks = [_make_task("p1", "escalated", gamer_tg_id=111)]
    _, markup = await main._build_dashboard_page(tasks, page=0, viewer_is_superadmin=False)
    all_cb = [btn.callback_data for row in markup.inline_keyboard for btn in row if hasattr(btn, 'callback_data') and btn.callback_data]
    assert any("release_pool:" in cb for cb in all_cb)
    assert any("release_finish:" in cb for cb in all_cb)


@pytest.mark.asyncio
async def test_build_dashboard_page_superadmin_no_action_buttons():
    """Superadmin viewer gets NO release_pool/finish/deny buttons."""
    import main
    tasks = [_make_task("p1", "escalated", gamer_tg_id=111)]
    _, markup = await main._build_dashboard_page(tasks, page=0, viewer_is_superadmin=True)
    all_cb = [btn.callback_data for row in markup.inline_keyboard for btn in row if hasattr(btn, 'callback_data') and btn.callback_data]
    assert not any("release_pool:" in cb for cb in all_cb)
    assert not any("release_finish:" in cb for cb in all_cb)


@pytest.mark.asyncio
async def test_build_dashboard_page_dm_button_url():
    """DM button has correct tg://user?id= URL."""
    import main
    tasks = [_make_task("p1", "escalated", gamer_tg_id=99999)]
    _, markup = await main._build_dashboard_page(tasks, page=0, viewer_is_superadmin=False)
    all_urls = [btn.url for row in markup.inline_keyboard for btn in row if hasattr(btn, 'url') and btn.url]
    assert any("tg://user?id=99999" in url for url in all_urls)


@pytest.mark.asyncio
async def test_build_dashboard_page_no_dm_button_when_no_tg_id():
    """No DM button when gamer has no Telegram ID."""
    import main
    tasks = [_make_task("p1", "escalated", gamer_tg_id=None)]
    _, markup = await main._build_dashboard_page(tasks, page=0, viewer_is_superadmin=False)
    all_urls = [btn.url for row in markup.inline_keyboard for btn in row if hasattr(btn, 'url') and btn.url]
    assert not any("tg://user?id=" in (url or "") for url in all_urls)


@pytest.mark.asyncio
async def test_build_dashboard_page_deny_button_only_for_pending_release():
    """release_deny button appears for pending_release items, not escalated items."""
    import main
    tasks = [
        _make_task("esc",     "escalated",       gamer_tg_id=1),
        _make_task("pending", "pending_release",  gamer_tg_id=2),
    ]
    _, markup = await main._build_dashboard_page(tasks, page=0, viewer_is_superadmin=False)
    all_cb = [btn.callback_data for row in markup.inline_keyboard for btn in row if hasattr(btn, 'callback_data') and btn.callback_data]
    assert any("release_deny:" in cb for cb in all_cb)
    # only one deny button (for the pending_release item)
    assert sum(1 for cb in all_cb if "release_deny:" in cb) == 1


@pytest.mark.asyncio
async def test_build_dashboard_page_pagination_first_page():
    """First page: no ◀️ button; ▶️ button present when more pages exist."""
    import main
    # 6 tasks → 2 pages of 5
    tasks = [_make_task(f"p{i}", "escalated", gamer_tg_id=i) for i in range(6)]
    _, markup = await main._build_dashboard_page(tasks, page=0, viewer_is_superadmin=False)
    nav_row = markup.inline_keyboard[-1]
    texts_in_nav = [btn.text for btn in nav_row]
    assert "◀️" not in texts_in_nav
    assert "▶️" in texts_in_nav


@pytest.mark.asyncio
async def test_build_dashboard_page_pagination_last_page():
    """Last page: ◀️ present; no ▶️ button."""
    import main
    tasks = [_make_task(f"p{i}", "escalated", gamer_tg_id=i) for i in range(6)]
    _, markup = await main._build_dashboard_page(tasks, page=1, viewer_is_superadmin=False)
    nav_row = markup.inline_keyboard[-1]
    texts_in_nav = [btn.text for btn in nav_row]
    assert "◀️" in texts_in_nav
    assert "▶️" not in texts_in_nav


@pytest.mark.asyncio
async def test_build_dashboard_page_empty_tasks_single_page():
    """With 0 tasks, total_pages=1, page indicator shows 1/1, no nav arrows."""
    import main
    text, markup = await main._build_dashboard_page([], page=0, viewer_is_superadmin=False)
    nav_row = markup.inline_keyboard[-1]
    texts_in_nav = [btn.text for btn in nav_row]
    assert "◀️" not in texts_in_nav
    assert "▶️" not in texts_in_nav
    assert any("1/1" in t for t in texts_in_nav)


# ---------------------------------------------------------------------------
# Task 4: DM button in progress_monitor._escalate()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalate_markup_has_dm_button_when_gamer_has_tg_id():
    """_escalate() sends a markup with a DM URL button when gamer has Telegram ID."""
    from progress_monitor import ProgressMonitor
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_bot = MagicMock()
    captured_markups = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        if reply_markup:
            captured_markups.append(reply_markup)
        return MagicMock()

    mock_bot.send_message = AsyncMock(side_effect=fake_send)
    mock_bot.forward_message = AsyncMock(return_value=MagicMock())

    gamer_oid = ObjectId()
    account = {
        "_id": ObjectId(),
        "profile": "test_acc",
        "status": "active",
        "gamer_id": gamer_oid,
        "progress_history": [],
        "ownership_history": [],
    }
    gamer = {"_id": gamer_oid, "id": 77777, "username": "testgamer"}

    mock_db = MagicMock()
    mock_db.get_gamer_by_id = AsyncMock(return_value=gamer)
    mock_db.set_account_status = AsyncMock(return_value=None)
    mock_db.get_support_users = AsyncMock(return_value=[{"id": 99, "username": "sup"}])

    pm = ProgressMonitor(mock_bot, mock_db)

    async def _fake_safe_wrap(fn):
        return await fn()

    with patch("utils.safe_wrap", new=AsyncMock(side_effect=_fake_safe_wrap)):
        await pm._escalate(account)

    assert captured_markups, "No markup was captured"
    markup = captured_markups[0]
    all_urls = [
        btn.url
        for row in markup.inline_keyboard
        for btn in row
        if hasattr(btn, "url") and btn.url
    ]
    assert any("tg://user?id=77777" in url for url in all_urls), \
        f"DM button with tg://user?id=77777 not found in {all_urls}"


@pytest.mark.asyncio
async def test_escalate_markup_no_dm_button_when_no_gamer():
    """_escalate() markup has no DM button when gamer_id is None."""
    from progress_monitor import ProgressMonitor
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_bot = MagicMock()
    captured_markups = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        if reply_markup:
            captured_markups.append(reply_markup)
        return MagicMock()

    mock_bot.send_message = AsyncMock(side_effect=fake_send)

    account = {
        "_id": ObjectId(),
        "profile": "orphan_acc",
        "status": "active",
        "gamer_id": None,
        "progress_history": [],
        "ownership_history": [],
    }

    mock_db = MagicMock()
    mock_db.get_gamer_by_id = AsyncMock(return_value=None)
    mock_db.set_account_status = AsyncMock(return_value=None)
    mock_db.get_support_users = AsyncMock(return_value=[{"id": 99}])

    pm = ProgressMonitor(mock_bot, mock_db)

    async def _fake_safe_wrap(fn):
        return await fn()

    with patch("utils.safe_wrap", new=AsyncMock(side_effect=_fake_safe_wrap)):
        await pm._escalate(account)

    for markup in captured_markups:
        all_urls = [
            btn.url
            for row in markup.inline_keyboard
            for btn in row
            if hasattr(btn, "url") and btn.url
        ]
        assert not any("tg://user?id=" in (url or "") for url in all_urls)


# ---------------------------------------------------------------------------
# Task 5: DM button in release request notification (gamer_release_account_select)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_release_request_notification_has_dm_button():
    """
    When a gamer requests account release, the notification sent to support
    must include a DM URL button with tg://user?id={gamer_tg_id}.
    """
    import main
    from unittest.mock import AsyncMock, MagicMock, patch
    from bson import ObjectId
    import datetime

    account_oid = ObjectId()
    gamer_oid = ObjectId()

    account = {
        "_id": account_oid,
        "profile": "test_profile",
        "status": "active",
        "gamer_id": gamer_oid,
        "progress_history": [
            {"gamer_id": gamer_oid, "synced_at": datetime.datetime.utcnow(),
             "tower_points": 100, "delta": 10}
        ],
        "ownership_history": [],
    }
    gamer = {"_id": gamer_oid, "id": 55555, "username": "releasegamer"}

    mock_db = MagicMock()
    mock_db.get_account_by_object_id = AsyncMock(return_value=account)
    mock_db.get_account = AsyncMock(return_value=account)
    mock_db.get_gamer = AsyncMock(return_value=gamer)
    mock_db.request_account_release = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_db.get_support_users = AsyncMock(return_value=[{"id": 888, "username": "sup"}])

    captured_markups = []

    async def fake_send(chat_id, text, reply_markup=None, **kw):
        if reply_markup:
            captured_markups.append(reply_markup)
        return MagicMock()

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(side_effect=fake_send)

    callback_query = MagicMock()
    callback_query.data = f"release_select:{account_oid}"
    callback_query.from_user.id = 55555
    callback_query.answer = AsyncMock(return_value=None)
    callback_query.message.chat.id = 55555

    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.set = AsyncMock(return_value=None)
    state.update_data = AsyncMock(return_value=None)

    mock_synchonizer = MagicMock()
    mock_synchonizer.sync_single_account = AsyncMock(return_value=None)

    async def _fake_safe_wrap(fn):
        return await fn()

    with patch.object(main, "db", mock_db), \
         patch.object(main, "bot", mock_bot), \
         patch.object(main, "synchonizer", mock_synchonizer), \
         patch.object(main, "TelegramState", _ts()), \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=_fake_safe_wrap)), \
         patch("utils.safe_wrap", new=AsyncMock(side_effect=_fake_safe_wrap)), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        await main.gamer_release_account_select(callback_query, state)

    assert captured_markups, "No markup sent to support"
    support_markup = captured_markups[0]
    all_urls = [
        btn.url
        for row in support_markup.inline_keyboard
        for btn in row
        if hasattr(btn, "url") and btn.url
    ]
    assert any("tg://user?id=55555" in url for url in all_urls), \
        f"DM button not found in {all_urls}"
