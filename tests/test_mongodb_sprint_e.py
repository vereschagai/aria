"""
Tests for Sprint E's new MongoDb methods in mongodb.py:
  - add_release_block
  - get_gamer_release_block_ids
  - increment_pool_release_count
  - finish_account
  - get_finished_accounts
  - pickup_account $nin exclusion of blocked accounts
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, AsyncMock
from bson import ObjectId
from datetime import datetime
import pymongo.errors

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bare_mongo_db():
    """Create a MongoDb instance with a fully mocked inner db, bypassing Motor."""
    from mongodb import MongoDb

    obj = object.__new__(MongoDb)
    obj.db = MagicMock()
    return obj


# ---------------------------------------------------------------------------
# add_release_block
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_release_block_inserts():
    """insert_one is called with the correct document shape."""
    obj = _bare_mongo_db()
    obj.db.release_blocks.insert_one = AsyncMock(return_value=None)

    account_id = ObjectId()
    gamer_id = ObjectId()
    reason = "pool_release"

    await obj.add_release_block(account_id, gamer_id, reason)

    obj.db.release_blocks.insert_one.assert_called_once()
    doc = obj.db.release_blocks.insert_one.call_args[0][0]
    assert doc["account_id"] == account_id
    assert doc["gamer_id"] == gamer_id
    assert doc["reason"] == reason
    assert "blocked_at" in doc


@pytest.mark.asyncio
async def test_add_release_block_duplicate_ignored():
    """DuplicateKeyError from insert_one is silently swallowed."""
    obj = _bare_mongo_db()
    obj.db.release_blocks.insert_one = AsyncMock(
        side_effect=pymongo.errors.DuplicateKeyError("", 11000)
    )

    # Must not raise
    await obj.add_release_block(ObjectId(), ObjectId(), "pool_release")


# ---------------------------------------------------------------------------
# get_gamer_release_block_ids
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_gamer_release_block_ids_returns_list():
    """Returns a flat list of account ObjectIds extracted from find results."""
    obj = _bare_mongo_db()
    oid1, oid2 = ObjectId(), ObjectId()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{"account_id": oid1}, {"account_id": oid2}])
    obj.db.release_blocks.find = MagicMock(return_value=cursor)

    result = await obj.get_gamer_release_block_ids(ObjectId())

    assert result == [oid1, oid2]


# ---------------------------------------------------------------------------
# increment_pool_release_count
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_increment_pool_release_count_returns_new_count():
    """Returns the updated pool_release_count from the post-update document."""
    obj = _bare_mongo_db()
    obj.db.gamers.find_one_and_update = AsyncMock(
        return_value={"_id": ObjectId(), "pool_release_count": 3}
    )

    result = await obj.increment_pool_release_count(ObjectId())

    assert result == 3


# ---------------------------------------------------------------------------
# finish_account
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_finish_account_sets_status_and_nulls_gamer():
    """Second update_one call sets status='finished' and gamer_id=None."""
    obj = _bare_mongo_db()
    obj.db.accounts.update_one = AsyncMock(return_value=None)

    now = datetime.utcnow()
    await obj.finish_account("acc1", support_id=42, now=now, tower_points=1234)

    assert obj.db.accounts.update_one.call_count == 2
    second_call = obj.db.accounts.update_one.call_args_list[1]
    set_fields = second_call[0][1]["$set"]
    assert set_fields["status"] == "finished"
    assert set_fields["gamer_id"] is None


@pytest.mark.asyncio
async def test_finish_account_closes_ownership_history():
    """First update_one call uses array_filters=[{'last.released_at': None}]."""
    obj = _bare_mongo_db()
    obj.db.accounts.update_one = AsyncMock(return_value=None)

    now = datetime.utcnow()
    await obj.finish_account("acc1", support_id=42, now=now, tower_points=500)

    first_call = obj.db.accounts.update_one.call_args_list[0]
    array_filters = first_call[1].get("array_filters")
    assert array_filters == [{"last.released_at": None}]


# ---------------------------------------------------------------------------
# get_finished_accounts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_finished_accounts_returns_list():
    """Returns a list of finished account docs from find().sort().to_list()."""
    obj = _bare_mongo_db()
    finished_doc = {"_id": ObjectId(), "profile": "acc1", "status": "finished"}
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[finished_doc])
    obj.db.accounts.find = MagicMock(return_value=cursor)

    result = await obj.get_finished_accounts()

    assert result == [finished_doc]


# ---------------------------------------------------------------------------
# pickup_account — blocked accounts excluded via $nin
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pickup_excludes_blocked_accounts():
    """pickup_account passes blocked account ids in $nin so they are never picked up."""
    obj = _bare_mongo_db()
    blocked_oid = ObjectId()
    gamer_oid = ObjectId()

    obj.get_gamer_release_block_ids = AsyncMock(return_value=[blocked_oid])

    # All find calls return empty — no accounts available
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[])
    obj.db.accounts.find = MagicMock(return_value=cursor)
    obj.db.gamers.find = MagicMock(return_value=cursor)

    result = await obj.pickup_account(gamer_oid)

    first_filter = obj.db.accounts.find.call_args_list[0][0][0]
    assert blocked_oid in first_filter["_id"]["$nin"]
    assert result is None
