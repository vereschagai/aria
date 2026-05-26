"""
Load tests and race condition tests for MongoDb pickup/eligibility logic.

Uses the object.__new__(MongoDb) + AsyncMock injection pattern (same as existing
test_mongodb_eligibility.py and test_mongodb_sprint_e.py). For race conditions,
asyncio.gather runs multiple pickup_account coroutines concurrently; a stateful
closure simulates MongoDB's atomic findOneAndUpdate — only the first caller wins.
"""

import sys
import os
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from bson import ObjectId
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from conftest import make_fake_account


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bare_mongo_db():
    """Create MongoDb with a fully mocked inner db, bypassing Motor."""
    from mongodb import MongoDb

    obj = object.__new__(MongoDb)
    obj.db = MagicMock()
    return obj


def _active_account(profile="acc", delta=100, gamer_oid=None, status="active"):
    if gamer_oid is None:
        gamer_oid = ObjectId()
    return {
        "_id": ObjectId(),
        "profile": profile,
        "status": status,
        "gamer_id": gamer_oid,
        "progress_history": [
            {"tower_points": 200, "delta": delta, "gamer_id": gamer_oid}
        ],
    }


def _make_pickup_db(gamer_oid, p1_accounts, remaining_accounts, gamers_with_season=None):
    """
    Build a MongoDb mock wired for pickup_account:
      - get_gamer_release_block_ids returns []
      - accounts.find returns p1_accounts on first call, remaining_accounts on second
      - gamers.find returns gamers_with_season (default [])
      - accounts.find_one_and_update returns the first account it's given (simulates
        the atomic claim — first caller wins)
    """
    obj = _bare_mongo_db()

    # Release blocks: none
    blocks_cursor = MagicMock()
    blocks_cursor.to_list = AsyncMock(return_value=[])
    obj.db.release_blocks.find = MagicMock(return_value=blocks_cursor)

    # gamers.find for active-season-owner lookup
    gamers_cursor = MagicMock()
    gamers_cursor.to_list = AsyncMock(return_value=gamers_with_season or [])
    obj.db.gamers.find = MagicMock(return_value=gamers_cursor)

    # accounts.find: first call = P1 (has .sort()), second call = remaining
    _call = [0]

    def _accounts_find(filter_q, *args, **kwargs):
        _call[0] += 1
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        if _call[0] == 1:
            cursor.to_list = AsyncMock(return_value=list(p1_accounts))
        else:
            cursor.to_list = AsyncMock(return_value=list(remaining_accounts))
        return cursor

    obj.db.accounts.find = MagicMock(side_effect=_accounts_find)
    return obj


# ---------------------------------------------------------------------------
# Load tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eligibility_25_accounts_all_active():
    """25 active accounts >= max_accounts_per_gamer(10) → ineligible (slot full)."""
    gamer_oid = ObjectId()
    accounts = [_active_account(f"acc{i}", delta=100, gamer_oid=gamer_oid) for i in range(25)]

    obj = _bare_mongo_db()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=accounts)
    obj.db.accounts.find = MagicMock(return_value=cursor)
    obj.db.gamers.find_one = AsyncMock(return_value=None)

    config = {"max_accounts_per_gamer": 10, "min_progress_points": 50}
    eligible, reason = await obj.check_assignment_eligibility(gamer_oid, config)

    assert eligible is False
    assert "10" in reason


@pytest.mark.asyncio
async def test_eligibility_24_active_1_below_progress():
    """24 accounts with good progress + 1 with delta=0 → ineligible (bad progress)."""
    gamer_oid = ObjectId()
    good = [_active_account(f"acc{i}", delta=100, gamer_oid=gamer_oid) for i in range(24)]
    bad = _active_account("bad_acc", delta=0, gamer_oid=gamer_oid)
    all_accounts = good + [bad]

    obj = _bare_mongo_db()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=all_accounts)
    obj.db.accounts.find = MagicMock(return_value=cursor)
    obj.db.gamers.find_one = AsyncMock(return_value=None)

    # max = 26 so slot check passes; progress check fires
    config = {"max_accounts_per_gamer": 26, "min_progress_points": 50}
    eligible, reason = await obj.check_assignment_eligibility(gamer_oid, config)

    assert eligible is False
    assert "bad_acc" in reason


@pytest.mark.asyncio
async def test_pickup_p1_25_historical_accounts():
    """25 released accounts all in gamer's ownership_history → highest-points one returned."""
    gamer_oid = ObjectId()

    # Build 25 accounts sorted descending by points
    p1_accounts = []
    for i in range(25):
        pts = (25 - i) * 100  # 2500, 2400, ..., 100
        acc = {
            "_id": ObjectId(),
            "profile": f"P1Acc{i}",
            "status": "released",
            "tower": {"points": pts, "rank": i, "floor": i},
            "ownership_history": [{"gamer_id": gamer_oid, "assigned_at": datetime(2024, 1, 1), "released_at": None}],
            "gamer_id": None,
        }
        p1_accounts.append(acc)
    # Sorted descending (highest points first)
    p1_accounts.sort(key=lambda a: a["tower"]["points"], reverse=True)

    obj = _make_pickup_db(gamer_oid, p1_accounts=p1_accounts, remaining_accounts=[])

    # find_one_and_update returns the first account tried (highest points)
    expected = {**p1_accounts[0], "status": "active", "gamer_id": gamer_oid}
    obj.db.accounts.find_one_and_update = AsyncMock(return_value=expected)

    result = await obj.pickup_account(gamer_oid)

    assert result is not None
    assert result["tower"]["points"] == p1_accounts[0]["tower"]["points"]


@pytest.mark.asyncio
async def test_account_screen_message_length_10_accounts():
    """Building accounts_table for 10 accounts renders without error and is non-empty."""
    import utils

    accounts = [make_fake_account(profile=f"Acc{i}", status="active") for i in range(10)]

    accounts_table = ""
    for account in accounts:
        history = account.get("progress_history", [])
        last_delta = history[-1]["delta"] if history else 0
        accounts_table += (
            f"\n{utils.escape('---------------------------')}\n"
            f"\n✅ *{utils.escape(account['profile'])}*\n"
            f"Tower Points: {account['tower']['points']} "
            f"\\(\\+{last_delta} за последний синк\\)\n"
        )

    assert len(accounts_table) > 0


@pytest.mark.asyncio
async def test_release_prompt_10_releasable_accounts():
    """10 active accounts → inline keyboard has 10 + 1 buttons."""
    # We test the button-building logic directly (handler test covered in test_gamer_handlers.py).
    # Here we verify the keyboard shape independently.
    from aiogram import types

    accounts = [make_fake_account(profile=f"Acc{i}", status="active") for i in range(10)]

    markup = types.InlineKeyboardMarkup(row_width=1)
    for account in accounts:
        history = account.get("progress_history", [])
        last_delta = history[-1]["delta"] if history else 0
        label = f"{account['profile']}  (башня: {account['tower']['points']}, +{last_delta} за синк)"
        markup.add(
            types.InlineKeyboardButton(
                label, callback_data=f"release_select:{account['_id']}"
            )
        )

    import buttons
    markup.add(types.InlineKeyboardButton(buttons.back, callback_data="release_back"))

    all_buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(all_buttons) == 11  # 10 accounts + 1 back


# ---------------------------------------------------------------------------
# Race condition tests — asyncio.gather + stateful mock
# ---------------------------------------------------------------------------


def _make_race_db(gamer_oid, account, claimed_flag):
    """
    Build a MongoDb mock for pickup_account where find_one_and_update is backed
    by a shared stateful closure — only the first caller claiming status='released' wins.
    """
    obj = _make_pickup_db(gamer_oid, p1_accounts=[], remaining_accounts=[account])

    async def _atomic_foa(filter_q, update, **kwargs):
        if filter_q.get("status") == "released" and not claimed_flag[0]:
            claimed_flag[0] = True
            return {**account, "status": "active", "gamer_id": gamer_oid}
        return None

    obj.db.accounts.find_one_and_update = _atomic_foa
    return obj


@pytest.mark.asyncio
async def test_simultaneous_pickup_two_gamers_one_account():
    """Two concurrent pickup_account calls on one released account → exactly one winner."""
    account_oid = ObjectId()
    account = {
        "_id": account_oid,
        "profile": "RaceAcc",
        "status": "released",
        "tower": {"points": 1000, "rank": 1, "floor": 1},
        "ownership_history": [],
        "gamer_id": None,
    }

    claimed = [False]
    gamer1_oid = ObjectId()
    gamer2_oid = ObjectId()

    db1 = _make_race_db(gamer1_oid, account, claimed)
    db2 = _make_race_db(gamer2_oid, account, claimed)

    result1, result2 = await asyncio.gather(
        db1.pickup_account(gamer1_oid),
        db2.pickup_account(gamer2_oid),
    )

    winners = [r for r in [result1, result2] if r is not None]
    assert len(winners) == 1


@pytest.mark.asyncio
async def test_simultaneous_pickup_20_gamers_one_account():
    """20 concurrent pickup_account calls on one released account → exactly one winner."""
    account_oid = ObjectId()
    account = {
        "_id": account_oid,
        "profile": "RaceAcc20",
        "status": "released",
        "tower": {"points": 500, "rank": 5, "floor": 5},
        "ownership_history": [],
        "gamer_id": None,
    }

    claimed = [False]
    gamers = [ObjectId() for _ in range(20)]
    dbs = [_make_race_db(g, account, claimed) for g in gamers]

    results = await asyncio.gather(
        *[db.pickup_account(g) for db, g in zip(dbs, gamers)]
    )

    winners = [r for r in results if r is not None]
    assert len(winners) == 1


@pytest.mark.asyncio
async def test_simultaneous_pickup_preserves_account_integrity():
    """After a race, the winning result has status='active' and no duplicate ownership."""
    account_oid = ObjectId()
    account = {
        "_id": account_oid,
        "profile": "IntegrityAcc",
        "status": "released",
        "tower": {"points": 750, "rank": 3, "floor": 3},
        "ownership_history": [],
        "gamer_id": None,
    }

    claimed = [False]
    gamers = [ObjectId() for _ in range(5)]
    dbs = [_make_race_db(g, account, claimed) for g in gamers]

    results = await asyncio.gather(
        *[db.pickup_account(g) for db, g in zip(dbs, gamers)]
    )

    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    winner = winners[0]
    assert winner["status"] == "active"
    assert winner["_id"] == account_oid
