import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
import time

# ---------------------------------------------------------------------------
# Shared helpers — mirrors conftest.py patterns
# ---------------------------------------------------------------------------

class _AsyncCursor:
    """Wraps a plain list as a Motor-style cursor with async to_list."""
    def __init__(self, items):
        self._items = items
    async def to_list(self, n):
        return self._items if n is None else self._items[:n]


class _FakeAccounts:
    """Minimal fake Motor collection for aggregate tests."""
    def __init__(self, docs):
        self._docs = docs

    def aggregate(self, pipeline):
        # Apply $match, $sort manually so the test is realistic
        status_filter = None
        sort_key = None
        for stage in pipeline:
            if "$match" in stage:
                status_filter = stage["$match"]["status"]["$in"]
            if "$sort" in stage:
                sort_key = list(stage["$sort"].keys())[0]
        results = [d for d in self._docs if d.get("status") in (status_filter or [])]
        if sort_key:
            results = sorted(results, key=lambda x: x.get(sort_key, ""))
        # Attach gamer as None (lookup not simulated — callers check None)
        for r in results:
            r.setdefault("gamer", None)
        return _AsyncCursor(results)

    def find(self, *a, **kw):
        return _AsyncCursor(self._docs)


# ---------------------------------------------------------------------------
# Task 1: F3 — get_open_support_tasks aggregation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_open_support_tasks_returns_only_escalated_and_pending():
    """Only escalated + pending_release accounts are returned."""
    from mongodb import MongoDb
    acc_escalated = {"_id": ObjectId(), "status": "escalated", "profile": "acc1", "gamer_id": None}
    acc_pending = {"_id": ObjectId(), "status": "pending_release", "profile": "acc2", "gamer_id": None}
    acc_active = {"_id": ObjectId(), "status": "active", "profile": "acc3", "gamer_id": None}

    db = MongoDb.__new__(MongoDb)
    db.db = MagicMock()
    db.db.accounts = _FakeAccounts([acc_escalated, acc_pending, acc_active])
    db.db.gamers = MagicMock()
    db.db.gamers.find_one = AsyncMock(return_value=None)

    result = await db.get_open_support_tasks()
    profiles = [r["profile"] for r in result]
    assert "acc1" in profiles
    assert "acc2" in profiles
    assert "acc3" not in profiles


@pytest.mark.asyncio
async def test_get_open_support_tasks_escalated_first():
    """Escalated accounts sort before pending_release."""
    from mongodb import MongoDb
    acc_pending = {"_id": ObjectId(), "status": "pending_release", "profile": "pending", "gamer_id": None}
    acc_escalated = {"_id": ObjectId(), "status": "escalated", "profile": "escalated", "gamer_id": None}

    db = MongoDb.__new__(MongoDb)
    db.db = MagicMock()
    db.db.accounts = _FakeAccounts([acc_pending, acc_escalated])  # wrong order intentionally
    db.db.gamers = MagicMock()
    db.db.gamers.find_one = AsyncMock(return_value=None)

    result = await db.get_open_support_tasks()
    assert result[0]["status"] == "escalated"
    assert result[1]["status"] == "pending_release"


# ---------------------------------------------------------------------------
# Task 2: F5 — Leaderboard TTL cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_leaderboard_cache_hit():
    """Second call within TTL returns cached data without hitting DB."""
    import mongodb as mongo_module
    # Clear cache state before test
    mongo_module._leaderboard_cache.clear()

    fake_result = [{"_id": ObjectId(), "total": 500}]

    db = mongo_module.MongoDb.__new__(mongo_module.MongoDb)
    db.db = MagicMock()

    call_count = 0
    async def fake_to_list(n):
        nonlocal call_count
        call_count += 1
        return fake_result

    cursor = MagicMock()
    cursor.to_list = fake_to_list
    db.db.accounts.aggregate = MagicMock(return_value=cursor)

    result1 = await db.get_all_gamers_season_points()
    result2 = await db.get_all_gamers_season_points()

    assert result1 == fake_result
    assert result2 == fake_result
    assert call_count == 1, f"Expected 1 DB call (cache hit on second), got {call_count}"


@pytest.mark.asyncio
async def test_leaderboard_cache_miss_after_ttl():
    """Call after TTL expires re-runs the aggregation."""
    import mongodb as mongo_module
    mongo_module._leaderboard_cache.clear()

    fake_result = [{"_id": ObjectId(), "total": 100}]

    db = mongo_module.MongoDb.__new__(mongo_module.MongoDb)
    db.db = MagicMock()

    call_count = 0
    async def fake_to_list(n):
        nonlocal call_count
        call_count += 1
        return fake_result

    cursor = MagicMock()
    cursor.to_list = fake_to_list
    db.db.accounts.aggregate = MagicMock(return_value=cursor)

    # Seed cache with an expired timestamp
    mongo_module._leaderboard_cache["data"] = fake_result
    mongo_module._leaderboard_cache["ts"] = time.time() - (mongo_module.LEADERBOARD_TTL_SECONDS + 1)

    await db.get_all_gamers_season_points()
    assert call_count == 1, "Should re-run aggregation after TTL expires"


# ---------------------------------------------------------------------------
# Task 4: F1 — Paginated gamer account screen
# ---------------------------------------------------------------------------

def _make_account_f(profile="TestProfile", points=1000, rank=50, floor=10,
                    login="user@test.com", password="pass123",
                    proxy_host="1.2.3.4", proxy_port="3128",
                    proxy_login="pl", proxy_pass="pp",
                    status="active", delta=100):
    return {
        "_id": ObjectId(),
        "profile": profile,
        "status": status,
        "tower": {"points": points, "rank": rank, "floor": floor},
        "login": login,
        "password": password,
        "proxy": {"host": proxy_host, "port": proxy_port,
                  "login": proxy_login, "password": proxy_pass},
        "progress_history": [{"delta": delta, "gamer_id": ObjectId()}]
    }


def _make_gamer_f(address="0xABC123"):
    return {
        "_id": ObjectId(),
        "id": 123456789,
        "username": "testgamer",
        "address": address,
        "referral": None,
    }


@pytest.mark.asyncio
async def test_account_page_pagination_counts():
    """25 accounts → page 0: 10, page 1: 10, page 2: 5."""
    from main import _build_account_page
    accounts = [_make_account_f(profile=f"Profile{i}", points=i * 100) for i in range(25)]
    gamer = _make_gamer_f()
    text0, _ = await _build_account_page(accounts, gamer, 0, {}, referral="Нет", referral_count=0, season_points=999)
    text1, _ = await _build_account_page(accounts, gamer, 1, {}, referral="Нет", referral_count=0, season_points=999)
    text2, _ = await _build_account_page(accounts, gamer, 2, {}, referral="Нет", referral_count=0, season_points=999)
    assert text0.count("Proxy:") == 10
    assert text1.count("Proxy:") == 10
    assert text2.count("Proxy:") == 5


@pytest.mark.asyncio
async def test_account_page_text_under_char_limit():
    """Every page must be under 4000 chars."""
    from main import _build_account_page
    accounts = [
        _make_account_f(profile="A" * 30, login="verylongemail@longdomain.example.com",
                        proxy_host="proxy.server.example.com", points=9999)
        for _ in range(10)
    ]
    gamer = _make_gamer_f()
    text, _ = await _build_account_page(accounts, gamer, 0, {}, referral="Нет", referral_count=0, season_points=9999)
    assert len(text) < 4000, f"Page text is {len(text)} chars, exceeds 4000-char limit"


@pytest.mark.asyncio
async def test_account_page_proxy_format_preserved():
    """Proxy block must contain Host:, Port:, Login:, Password: labels."""
    from main import _build_account_page
    accounts = [_make_account_f()]
    gamer = _make_gamer_f()
    text, _ = await _build_account_page(accounts, gamer, 0, {}, referral="Нет", referral_count=0, season_points=0)
    assert "Proxy:" in text
    assert "Host:" in text
    assert "Port:" in text
    assert "Login:" in text
    assert "Password:" in text


# ---------------------------------------------------------------------------
# Task 5: F2 — Paginated release account selector
# ---------------------------------------------------------------------------

def test_release_page_pagination_counts():
    """15 releasable accounts → page 0: 10 buttons + nav, page 1: 5 buttons + nav."""
    from main import _build_release_page

    accounts = [
        _make_account_f(profile=f"Profile{i}", points=i * 50)
        for i in range(15)
    ]

    markup0 = _build_release_page(accounts, page=0)
    markup1 = _build_release_page(accounts, page=1)

    def count_release_buttons(markup):
        count = 0
        for row in markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("release_select:"):
                    count += 1
        return count

    def has_back_button(markup):
        for row in markup.inline_keyboard:
            for btn in row:
                if btn.callback_data == "release_back":
                    return True
        return False

    assert count_release_buttons(markup0) == 10
    assert count_release_buttons(markup1) == 5
    assert has_back_button(markup0)
    assert has_back_button(markup1)
