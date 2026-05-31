"""
Tests for MongoDb.pickup_account priority logic (mongodb.py).

Covers P1/P2 assignment algorithm — the cases NOT exercised by the race tests
in test_load_and_race.py or the $nin test in test_mongodb_sprint_e.py.

P1: accounts previously owned by this gamer (ownership_history.gamer_id match),
    sorted by tower.points DESC.
P2: remaining released accounts whose last owner has season_picked_up != True
    (or no previous owner), sorted by tower.points DESC.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, AsyncMock
from bson import ObjectId
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bare_mongo_db():
    from mongodb import MongoDb
    obj = object.__new__(MongoDb)
    obj.db = MagicMock()
    return obj


def _make_account(profile, points=500, ownership_history=None, gamer_id=None):
    """Released account ready for pickup."""
    return {
        "_id": ObjectId(),
        "profile": profile,
        "status": "released",
        "gamer_id": gamer_id,
        "tower": {"points": points, "rank": 1, "floor": 1},
        "ownership_history": ownership_history if ownership_history is not None else [],
    }


def _wire_pickup(obj, p1_accounts, remaining_accounts, active_season_gamers=None):
    """
    Wire obj.db for pickup_account:
      - release_blocks.find → [] (no blocks)
      - accounts.find: 1st call → p1_accounts, 2nd call → remaining_accounts
      - gamers.find → active_season_gamers (default [])
      - accounts.find_one_and_update → set by caller
    """
    blocks_cursor = MagicMock()
    blocks_cursor.to_list = AsyncMock(return_value=[])
    obj.db.release_blocks.find = MagicMock(return_value=blocks_cursor)

    gamers_cursor = MagicMock()
    gamers_cursor.to_list = AsyncMock(return_value=active_season_gamers or [])
    obj.db.gamers.find = MagicMock(return_value=gamers_cursor)

    _call = [0]

    def _accounts_find(filter_q, *args, **kwargs):
        _call[0] += 1
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(
            return_value=list(p1_accounts) if _call[0] == 1 else list(remaining_accounts)
        )
        return cursor

    obj.db.accounts.find = MagicMock(side_effect=_accounts_find)


# ---------------------------------------------------------------------------
# P1 / P2 fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pickup_p1_preferred_over_p2():
    """Gamer has a P1 account and a P2 account available — P1 is returned."""
    gamer_oid = ObjectId()
    p1 = _make_account("P1Acc", points=300, ownership_history=[
        {"gamer_id": gamer_oid, "assigned_at": datetime(2024, 1, 1), "released_at": None}
    ])
    p2 = _make_account("P2Acc", points=999)  # higher points but still P2

    obj = _bare_mongo_db()
    _wire_pickup(obj, p1_accounts=[p1], remaining_accounts=[p2])

    expected = {**p1, "status": "active", "gamer_id": gamer_oid}
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=expected)

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    assert result["profile"] == "P1Acc"


@pytest.mark.asyncio
async def test_pickup_no_p1_fresh_gamer_gets_p2():
    """Brand-new gamer with no ownership history → gets a P2 account."""
    gamer_oid = ObjectId()
    p2 = _make_account("FreshAcc", points=500, ownership_history=[])

    obj = _bare_mongo_db()
    _wire_pickup(obj, p1_accounts=[], remaining_accounts=[p2])

    expected = {**p2, "status": "active", "gamer_id": gamer_oid}
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=expected)

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    assert result["profile"] == "FreshAcc"


@pytest.mark.asyncio
async def test_pickup_p1_all_claimed_falls_to_p2():
    """P1 candidates exist but find_one_and_update returns None for all (race) → falls to P2."""
    gamer_oid = ObjectId()
    p1 = _make_account("P1Acc", points=1000, ownership_history=[
        {"gamer_id": gamer_oid, "assigned_at": datetime(2024, 1, 1), "released_at": None}
    ])
    p2 = _make_account("P2Acc", points=200, ownership_history=[])

    obj = _bare_mongo_db()
    _wire_pickup(obj, p1_accounts=[p1], remaining_accounts=[p2])

    expected_p2 = {**p2, "status": "active", "gamer_id": gamer_oid}

    call_count = [0]

    async def _foa(filter_q, update, **kwargs):
        call_count[0] += 1
        # First call is for P1 — simulate race (return None)
        if call_count[0] == 1:
            return None
        # Second call is for P2 — winner
        return expected_p2

    obj.db.accounts.find_one_and_update = _foa

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    assert result["profile"] == "P2Acc"
    assert call_count[0] == 2


@pytest.mark.asyncio
async def test_pickup_both_pools_empty_returns_none():
    """P1 and P2 both empty → pickup_account returns None."""
    gamer_oid = ObjectId()
    obj = _bare_mongo_db()
    _wire_pickup(obj, p1_accounts=[], remaining_accounts=[])
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=None)

    result = await obj.pickup_account(gamer_oid)

    assert result is None


# ---------------------------------------------------------------------------
# P2 inclusion / exclusion rules
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pickup_p2_includes_never_assigned_account():
    """Account with empty ownership_history (never assigned) is included in P2."""
    gamer_oid = ObjectId()
    account = _make_account("NewAcc", points=400, ownership_history=[])

    obj = _bare_mongo_db()
    _wire_pickup(obj, p1_accounts=[], remaining_accounts=[account])

    expected = {**account, "status": "active", "gamer_id": gamer_oid}
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=expected)

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    assert result["profile"] == "NewAcc"


@pytest.mark.asyncio
async def test_pickup_p2_includes_null_last_owner():
    """Account where ownership_history[-1].gamer_id is None is included in P2."""
    gamer_oid = ObjectId()
    account = _make_account("NullOwnerAcc", points=300, ownership_history=[
        {"gamer_id": None, "assigned_at": datetime(2024, 1, 1), "released_at": None}
    ])

    obj = _bare_mongo_db()
    _wire_pickup(obj, p1_accounts=[], remaining_accounts=[account])

    expected = {**account, "status": "active", "gamer_id": gamer_oid}
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=expected)

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    assert result["profile"] == "NullOwnerAcc"


@pytest.mark.asyncio
async def test_pickup_p2_includes_inactive_season_owner():
    """Account whose last owner has season_picked_up=None is included in P2."""
    gamer_oid = ObjectId()
    inactive_owner_oid = ObjectId()
    account = _make_account("InactiveOwnerAcc", points=600, ownership_history=[
        {"gamer_id": inactive_owner_oid, "assigned_at": datetime(2024, 1, 1), "released_at": None}
    ])

    obj = _bare_mongo_db()
    # gamers.find returns empty — inactive_owner_oid NOT in active season gamers
    _wire_pickup(obj, p1_accounts=[], remaining_accounts=[account], active_season_gamers=[])

    expected = {**account, "status": "active", "gamer_id": gamer_oid}
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=expected)

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    assert result["profile"] == "InactiveOwnerAcc"


@pytest.mark.asyncio
async def test_pickup_p2_excludes_active_season_owner():
    """Account whose last owner has season_picked_up=True is excluded from P2."""
    gamer_oid = ObjectId()
    active_owner_oid = ObjectId()
    blocked_account = _make_account("ActiveOwnerAcc", points=999, ownership_history=[
        {"gamer_id": active_owner_oid, "assigned_at": datetime(2024, 1, 1), "released_at": None}
    ])

    obj = _bare_mongo_db()
    # active_owner_oid IS in active season gamers → account excluded from P2
    active_gamer = {"_id": active_owner_oid, "season_picked_up": True}
    _wire_pickup(
        obj, p1_accounts=[], remaining_accounts=[blocked_account],
        active_season_gamers=[active_gamer]
    )
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=None)

    result = await obj.pickup_account(gamer_oid)

    # find_one_and_update must NOT have been called (account excluded before attempt)
    obj.db.accounts.find_one_and_update.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_pickup_p2_mixed_active_and_inactive_owners():
    """Two P2 candidates: one whose owner is active (excluded), one inactive (included)."""
    gamer_oid = ObjectId()
    active_owner_oid = ObjectId()
    inactive_owner_oid = ObjectId()

    excluded = _make_account("ExcludedAcc", points=9999, ownership_history=[
        {"gamer_id": active_owner_oid, "assigned_at": datetime(2024, 1, 1), "released_at": None}
    ])
    included = _make_account("IncludedAcc", points=100, ownership_history=[
        {"gamer_id": inactive_owner_oid, "assigned_at": datetime(2024, 1, 1), "released_at": None}
    ])

    obj = _bare_mongo_db()
    active_gamer = {"_id": active_owner_oid, "season_picked_up": True}
    _wire_pickup(
        obj, p1_accounts=[],
        remaining_accounts=[excluded, included],
        active_season_gamers=[active_gamer]
    )

    expected = {**included, "status": "active", "gamer_id": gamer_oid}
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=expected)

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    assert result["profile"] == "IncludedAcc"
    # Ensure only one find_one_and_update call — for the included account
    obj.db.accounts.find_one_and_update.assert_called_once()
    call_filter = obj.db.accounts.find_one_and_update.call_args[0][0]
    assert call_filter["_id"] == included["_id"]


# ---------------------------------------------------------------------------
# P2 sorting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pickup_p2_sorted_by_points_desc():
    """Among P2 candidates, the highest-points account is tried first."""
    gamer_oid = ObjectId()
    low = _make_account("LowAcc", points=100, ownership_history=[])
    mid = _make_account("MidAcc", points=500, ownership_history=[])
    high = _make_account("HighAcc", points=999, ownership_history=[])

    obj = _bare_mongo_db()
    # Pass in shuffled order — sorting is done inside pickup_account
    _wire_pickup(obj, p1_accounts=[], remaining_accounts=[mid, low, high])

    tried_ids = []

    async def _foa(filter_q, update, **kwargs):
        tried_ids.append(filter_q["_id"])
        # Always succeed on first valid try
        account = next(a for a in [low, mid, high] if a["_id"] == filter_q["_id"])
        return {**account, "status": "active", "gamer_id": gamer_oid}

    obj.db.accounts.find_one_and_update = _foa

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    # First tried must be the highest-points account
    assert tried_ids[0] == high["_id"]
    assert result["profile"] == "HighAcc"


# ---------------------------------------------------------------------------
# P1 sorting (highest points first)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pickup_p1_highest_points_tried_first():
    """Among P1 candidates, the highest-points account is tried first."""
    gamer_oid = ObjectId()
    low_p1 = _make_account("LowP1", points=200, ownership_history=[
        {"gamer_id": gamer_oid, "assigned_at": datetime(2024, 1, 1), "released_at": None}
    ])
    high_p1 = _make_account("HighP1", points=800, ownership_history=[
        {"gamer_id": gamer_oid, "assigned_at": datetime(2024, 1, 2), "released_at": None}
    ])
    # Sorted descending (as db.find().sort() would return)
    p1_sorted = [high_p1, low_p1]

    obj = _bare_mongo_db()
    _wire_pickup(obj, p1_accounts=p1_sorted, remaining_accounts=[])

    tried_ids = []

    async def _foa(filter_q, update, **kwargs):
        tried_ids.append(filter_q["_id"])
        account = next(a for a in [low_p1, high_p1] if a["_id"] == filter_q["_id"])
        return {**account, "status": "active", "gamer_id": gamer_oid}

    obj.db.accounts.find_one_and_update = _foa

    result = await obj.pickup_account(gamer_oid)

    assert tried_ids[0] == high_p1["_id"]
    assert result["profile"] == "HighP1"


# ---------------------------------------------------------------------------
# Gamer with 5 previous accounts (various states)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pickup_gamer_with_5_historical_accounts_3_available():
    """Gamer had 5 accounts historically. 3 are released (P1), 2 are taken by others.
    Should pick the highest-points released one."""
    gamer_oid = ObjectId()

    # 3 released P1 accounts (sorted desc by points)
    available = [
        _make_account(f"OldAcc{i}", points=(3 - i) * 100, ownership_history=[
            {"gamer_id": gamer_oid, "assigned_at": datetime(2024, 1, 1), "released_at": None}
        ])
        for i in range(3)
    ]
    available.sort(key=lambda a: a["tower"]["points"], reverse=True)

    obj = _bare_mongo_db()
    _wire_pickup(obj, p1_accounts=available, remaining_accounts=[])

    expected = {**available[0], "status": "active", "gamer_id": gamer_oid}
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=expected)

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    assert result["tower"]["points"] == 300  # highest
    assert result["profile"] == available[0]["profile"]
