"""
Tests for MongoDb.check_assignment_eligibility (mongodb.py).

BRD requirement covered: Season 4 assignment eligibility gate.
  - Slot limit (active + escalated + pending_release) < max_accounts_per_gamer.
  - All strictly 'active' accounts must have delta >= min_progress_points
    in their last progress_history entry attributed to this gamer.
  - Escalated/pending_release accounts are slot-counted but exempt from progress check.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mongo_db(occupied_accounts: list):
    """
    Build a minimal MongoDb-like object where check_assignment_eligibility
    can run. The method uses self.db.accounts.find(...).to_list(None) internally.
    """
    # Create a bare instance without calling __init__ (avoids motor connection)
    from mongodb import MongoDb
    obj = object.__new__(MongoDb)

    # Mock the inner motor database
    mock_inner_db = MagicMock()
    obj.db = mock_inner_db

    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=occupied_accounts)
    mock_inner_db.accounts.find = MagicMock(return_value=cursor)

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_at_slot_limit_ineligible():
    """Case 1: occupied slots >= max → ineligible."""
    gamer_oid = ObjectId()
    accounts = [_active_account(f"acc{i}", gamer_oid=gamer_oid) for i in range(10)]
    mongo = _make_mongo_db(accounts)

    config = {"max_accounts_per_gamer": 10, "min_progress_points": 50}
    eligible, reason = await mongo.check_assignment_eligibility(gamer_oid, config)

    assert eligible is False
    assert "10" in reason


@pytest.mark.asyncio
async def test_under_limit_all_good_progress_eligible():
    """Case 2: under slot limit, all active accounts have delta >= min → eligible."""
    gamer_oid = ObjectId()
    accounts = [_active_account("acc1", delta=100, gamer_oid=gamer_oid)]
    mongo = _make_mongo_db(accounts)

    config = {"max_accounts_per_gamer": 10, "min_progress_points": 50}
    eligible, reason = await mongo.check_assignment_eligibility(gamer_oid, config)

    assert eligible is True
    assert reason == "ok"


@pytest.mark.asyncio
async def test_under_limit_bad_progress_ineligible():
    """Case 3: one active account with delta < min → ineligible."""
    gamer_oid = ObjectId()
    accounts = [_active_account("acc1", delta=10, gamer_oid=gamer_oid)]
    mongo = _make_mongo_db(accounts)

    config = {"max_accounts_per_gamer": 10, "min_progress_points": 50}
    eligible, reason = await mongo.check_assignment_eligibility(gamer_oid, config)

    assert eligible is False
    assert "acc1" in reason


@pytest.mark.asyncio
async def test_pending_release_counted_not_checked():
    """Case 4: pending_release account is counted for slots but not progress-checked."""
    gamer_oid = ObjectId()
    # One pending_release (no progress_history) + one active with good progress
    pending = {
        "_id": ObjectId(),
        "profile": "pending_acc",
        "status": "pending_release",
        "gamer_id": gamer_oid,
        "progress_history": [],  # would fail progress check if wrongly checked
    }
    active_good = _active_account("acc_good", delta=200, gamer_oid=gamer_oid)
    mongo = _make_mongo_db([pending, active_good])

    config = {"max_accounts_per_gamer": 10, "min_progress_points": 50}
    eligible, reason = await mongo.check_assignment_eligibility(gamer_oid, config)

    assert eligible is True


@pytest.mark.asyncio
async def test_escalated_counted_not_checked():
    """Case 5: escalated account counted for slots but does NOT block eligibility."""
    gamer_oid = ObjectId()
    escalated = {
        "_id": ObjectId(),
        "profile": "esc_acc",
        "status": "escalated",
        "gamer_id": gamer_oid,
        "progress_history": [],  # empty — would fail if wrongly checked
    }
    active_good = _active_account("acc_good", delta=100, gamer_oid=gamer_oid)
    mongo = _make_mongo_db([escalated, active_good])

    config = {"max_accounts_per_gamer": 10, "min_progress_points": 50}
    eligible, reason = await mongo.check_assignment_eligibility(gamer_oid, config)

    assert eligible is True


@pytest.mark.asyncio
async def test_empty_progress_history_ineligible():
    """Case 6: active account with empty progress_history → ineligible (no data)."""
    gamer_oid = ObjectId()
    acc = {
        "_id": ObjectId(),
        "profile": "empty_hist",
        "status": "active",
        "gamer_id": gamer_oid,
        "progress_history": [],
    }
    mongo = _make_mongo_db([acc])

    config = {"max_accounts_per_gamer": 10, "min_progress_points": 50}
    eligible, reason = await mongo.check_assignment_eligibility(gamer_oid, config)

    assert eligible is False
    assert "empty_hist" in reason


@pytest.mark.asyncio
async def test_progress_from_different_gamer_ineligible():
    """Case 7: last progress_history entry attributed to a different gamer → ineligible."""
    gamer_oid = ObjectId()
    other_gamer_oid = ObjectId()
    acc = {
        "_id": ObjectId(),
        "profile": "other_owner",
        "status": "active",
        "gamer_id": gamer_oid,
        "progress_history": [
            {"tower_points": 300, "delta": 200, "gamer_id": other_gamer_oid}
        ],
    }
    mongo = _make_mongo_db([acc])

    config = {"max_accounts_per_gamer": 10, "min_progress_points": 50}
    eligible, reason = await mongo.check_assignment_eligibility(gamer_oid, config)

    assert eligible is False
    assert "other_owner" in reason
