"""
Tests for ProgressMonitor (progress_monitor.py).

BRD requirement covered: inactivity detection and escalation logic.
  - 1-day inactivity → warn gamer once per calendar day.
  - N-day inactivity (inactivity_escalation_days) → escalate to support.
  - Deduplication via last_notified_day ordinal.
  - pending_release / escalated accounts are excluded from the inactivity check.
"""

import sys
import os
import pytest
import asyncio
from datetime import datetime, timedelta, date
from unittest.mock import MagicMock, AsyncMock, patch, call
from bson import ObjectId

# ---------------------------------------------------------------------------
# Path setup — allow imports from the project root
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch utils.safe_wrap BEFORE importing progress_monitor so the retry decorator
# is never reached during tests.
async def _simple_safe_wrap(corofn):
    return await corofn()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _account(
    profile="acc1",
    status="active",
    gamer_id=None,
    days_inactive=2,
    last_notified_day=None,
    has_ownership_history=True,
    has_last_progress=True,
):
    """Build a minimal account dict for test scenarios."""
    if gamer_id is None:
        gamer_id = ObjectId()

    baseline = datetime.now() - timedelta(days=days_inactive)

    acc = {
        "_id": ObjectId(),
        "profile": profile,
        "status": status,
        "gamer_id": gamer_id,
        "last_notified_day": last_notified_day,
        "progress_history": [],
    }

    if has_last_progress:
        acc["last_progress_at"] = baseline
    else:
        acc["last_progress_at"] = None
        if has_ownership_history:
            acc["ownership_history"] = [{"assigned_at": baseline}]
        else:
            acc["ownership_history"] = []

    return acc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_accounts_does_nothing(mock_db, mock_bot, base_config):
    """Case 1: empty account list — no bot calls made."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor
        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[])

        pm = ProgressMonitor(mock_bot, mock_db)
        await pm.check_all()

        mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_active_account_no_progress_history_skipped(mock_db, mock_bot, base_config):
    """Case 2: active account with no progress_history AND no ownership_history → skipped."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        acc = {
            "_id": ObjectId(),
            "profile": "acc_new",
            "status": "active",
            "gamer_id": ObjectId(),
            "last_progress_at": None,
            "last_notified_day": None,
            "ownership_history": [],  # no baseline → must be skipped
        }

        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[acc])

        pm = ProgressMonitor(mock_bot, mock_db)
        await pm.check_all()

        mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_warn_on_day_1(mock_db, mock_bot, base_config):
    """Case 3: active account with days_inactive=1 → _warn_gamer called."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        gamer_oid = ObjectId()
        acc = _account(days_inactive=1, gamer_id=gamer_oid)
        gamer = {"_id": gamer_oid, "id": 111111, "username": "testuser"}

        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[acc])
        mock_db.get_gamer_by_id = AsyncMock(return_value=gamer)
        mock_db.get_support_users = AsyncMock(return_value=[])

        pm = ProgressMonitor(mock_bot, mock_db)
        with patch.object(pm, "_warn_gamer", new=AsyncMock()) as mock_warn:
            await pm.check_all()
            mock_warn.assert_called_once()
            mock_warn.assert_called_with(acc, 1)


@pytest.mark.asyncio
async def test_warn_on_day_2(mock_db, mock_bot, base_config):
    """Case 4: days_inactive=2 (still below escalation threshold of 3) → warn, not escalate."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        gamer_oid = ObjectId()
        acc = _account(days_inactive=2, gamer_id=gamer_oid)

        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[acc])

        pm = ProgressMonitor(mock_bot, mock_db)
        with patch.object(pm, "_warn_gamer", new=AsyncMock()) as mock_warn, \
             patch.object(pm, "_escalate", new=AsyncMock()) as mock_escalate:
            await pm.check_all()
            mock_warn.assert_called_once()
            mock_escalate.assert_not_called()


@pytest.mark.asyncio
async def test_escalate_on_day_3(mock_db, mock_bot, base_config):
    """Case 5: days_inactive >= inactivity_escalation_days (3) → _escalate called, not warn."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        gamer_oid = ObjectId()
        acc = _account(days_inactive=3, gamer_id=gamer_oid)

        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[acc])

        pm = ProgressMonitor(mock_bot, mock_db)
        with patch.object(pm, "_warn_gamer", new=AsyncMock()) as mock_warn, \
             patch.object(pm, "_escalate", new=AsyncMock()) as mock_escalate:
            await pm.check_all()
            mock_escalate.assert_called_once_with(acc)
            mock_warn.assert_not_called()


@pytest.mark.asyncio
async def test_deduplication_same_day(mock_db, mock_bot, base_config):
    """Case 6: last_notified_day == today's ordinal → neither warn nor escalate."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        today_ordinal = date.today().toordinal()
        gamer_oid = ObjectId()
        acc = _account(days_inactive=2, gamer_id=gamer_oid, last_notified_day=today_ordinal)

        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[acc])

        pm = ProgressMonitor(mock_bot, mock_db)
        with patch.object(pm, "_warn_gamer", new=AsyncMock()) as mock_warn, \
             patch.object(pm, "_escalate", new=AsyncMock()) as mock_escalate:
            await pm.check_all()
            mock_warn.assert_not_called()
            mock_escalate.assert_not_called()


@pytest.mark.asyncio
async def test_pending_release_excluded(mock_db, mock_bot, base_config):
    """Case 7: pending_release accounts are NOT returned by get_active_assigned_accounts
    (that query filters status=active), so they never reach the inactivity check."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        # get_active_assigned_accounts only returns status=active accounts.
        # Simulate that correctly: return empty list (pending_release excluded).
        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[])

        pm = ProgressMonitor(mock_bot, mock_db)
        with patch.object(pm, "_warn_gamer", new=AsyncMock()) as mock_warn, \
             patch.object(pm, "_escalate", new=AsyncMock()) as mock_escalate:
            await pm.check_all()
            mock_warn.assert_not_called()
            mock_escalate.assert_not_called()


@pytest.mark.asyncio
async def test_gamer_without_telegram_id_skipped(mock_db, mock_bot, base_config):
    """Case 8: gamer has no 'id' field → _warn_gamer exits safely without sending."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        gamer_oid = ObjectId()
        acc = _account(days_inactive=1, gamer_id=gamer_oid)
        # gamer doc missing 'id' key
        gamer_no_tg = {"_id": gamer_oid, "username": "ghost"}

        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[acc])
        mock_db.get_gamer_by_id = AsyncMock(return_value=gamer_no_tg)

        pm = ProgressMonitor(mock_bot, mock_db)
        # Should not raise; send_message must never be called
        await pm.check_all()
        mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_escalated_account_no_warning(mock_db, mock_bot, base_config):
    """Case 9: account already status=escalated → elif guard prevents _warn_gamer."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        gamer_oid = ObjectId()
        acc = _account(days_inactive=1, gamer_id=gamer_oid, status="escalated")

        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[acc])

        pm = ProgressMonitor(mock_bot, mock_db)
        with patch.object(pm, "_warn_gamer", new=AsyncMock()) as mock_warn, \
             patch.object(pm, "_escalate", new=AsyncMock()) as mock_escalate:
            await pm.check_all()
            mock_warn.assert_not_called()
            mock_escalate.assert_not_called()


@pytest.mark.asyncio
async def test_escalate_day_5_custom_threshold(mock_db, mock_bot):
    """Case 10: custom escalation threshold of 5 days — day 5 triggers escalation."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        config = {"inactivity_escalation_days": 5, "min_progress_points": 50,
                  "max_accounts_per_gamer": 10}
        gamer_oid = ObjectId()
        acc = _account(days_inactive=5, gamer_id=gamer_oid)

        mock_db.get_config = AsyncMock(return_value=config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[acc])

        pm = ProgressMonitor(mock_bot, mock_db)
        with patch.object(pm, "_warn_gamer", new=AsyncMock()) as mock_warn, \
             patch.object(pm, "_escalate", new=AsyncMock()) as mock_escalate:
            await pm.check_all()
            mock_escalate.assert_called_once_with(acc)
            mock_warn.assert_not_called()


@pytest.mark.asyncio
async def test_baseline_from_ownership_history(mock_db, mock_bot, base_config):
    """Case 11: no last_progress_at → ownership_history[-1].assigned_at used as baseline."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        gamer_oid = ObjectId()
        acc = _account(days_inactive=0, gamer_id=gamer_oid,
                       has_last_progress=False, has_ownership_history=True)
        # Override ownership_history assigned_at to 2 days ago
        from datetime import timedelta
        acc["ownership_history"][0]["assigned_at"] = datetime.now() - timedelta(days=2)

        mock_db.get_config = AsyncMock(return_value=base_config)
        mock_db.get_active_assigned_accounts = AsyncMock(return_value=[acc])

        pm = ProgressMonitor(mock_bot, mock_db)
        with patch.object(pm, "_warn_gamer", new=AsyncMock()) as mock_warn, \
             patch.object(pm, "_escalate", new=AsyncMock()) as mock_escalate:
            await pm.check_all()
            # 2 days inactive (< 3), so warn not escalate
            mock_warn.assert_called_once()
            mock_escalate.assert_not_called()


# ---------------------------------------------------------------------------
# Direct _warn_gamer unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_warn_gamer_gamer_not_found_silent(mock_db, mock_bot):
    """_warn_gamer: get_gamer_by_id returns None → no send_message, no error."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        mock_db.get_gamer_by_id = AsyncMock(return_value=None)
        pm = ProgressMonitor(mock_bot, mock_db)
        account = {"profile": "Acc", "gamer_id": ObjectId()}

        await pm._warn_gamer(account, days_inactive=1)

        mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_warn_gamer_sends_to_correct_telegram_id(mock_db, mock_bot):
    """_warn_gamer: gamer found → send_message called with gamer's Telegram id."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        gamer_oid = ObjectId()
        gamer = {"_id": gamer_oid, "id": 99999, "username": "player"}
        mock_db.get_gamer_by_id = AsyncMock(return_value=gamer)
        pm = ProgressMonitor(mock_bot, mock_db)
        account = {"profile": "Acc", "gamer_id": gamer_oid}

        await pm._warn_gamer(account, days_inactive=2)

        mock_bot.send_message.assert_called_once()
        assert mock_bot.send_message.call_args[0][0] == 99999


# ---------------------------------------------------------------------------
# Direct _escalate unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalate_no_support_users_still_marks_escalated(mock_db, mock_bot):
    """_escalate: empty support list → set_account_status('escalated') still called."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        mock_db.get_gamer_by_id = AsyncMock(return_value=None)
        mock_db.get_support_users = AsyncMock(return_value=[])
        pm = ProgressMonitor(mock_bot, mock_db)
        account = {
            "_id": ObjectId(), "profile": "Acc",
            "gamer_id": None, "status": "active",
            "progress_history": [], "ownership_history": [],
        }

        await pm._escalate(account)

        mock_db.set_account_status.assert_called_once()
        assert mock_db.set_account_status.call_args[0][1] == "escalated"
        mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_escalate_sets_escalated_at_and_notified_day(mock_db, mock_bot):
    """_escalate: extra_fields passed to set_account_status include escalated_at and last_notified_day."""
    import utils as _utils_mod
    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        gamer_oid = ObjectId()
        gamer = {"_id": gamer_oid, "id": 55555, "username": "player"}
        mock_db.get_gamer_by_id = AsyncMock(return_value=gamer)
        mock_db.get_support_users = AsyncMock(return_value=[{"id": 99}])
        pm = ProgressMonitor(mock_bot, mock_db)
        account = {
            "_id": ObjectId(), "profile": "Acc",
            "gamer_id": gamer_oid, "status": "active",
            "progress_history": [], "ownership_history": [],
        }

        await pm._escalate(account)

        mock_db.set_account_status.assert_called_once()
        extra = mock_db.set_account_status.call_args[1].get("extra_fields") or \
                mock_db.set_account_status.call_args[0][2]
        assert "escalated_at" in extra
        assert "last_notified_day" in extra


@pytest.mark.asyncio
async def test_escalate_support_failure_continues_to_next(mock_db, mock_bot):
    """_escalate: first support user send fails → second support user still notified."""
    import utils as _utils_mod

    call_ids = []

    async def _flaky_send(chat_id, text, **kwargs):
        call_ids.append(chat_id)
        if chat_id == 101:
            raise Exception("Telegram error")
        return MagicMock()

    mock_bot.send_message = AsyncMock(side_effect=_flaky_send)

    with patch.object(_utils_mod, "safe_wrap", side_effect=_simple_safe_wrap):
        from progress_monitor import ProgressMonitor

        mock_db.get_gamer_by_id = AsyncMock(return_value=None)
        mock_db.get_support_users = AsyncMock(return_value=[{"id": 101}, {"id": 102}])
        pm = ProgressMonitor(mock_bot, mock_db)
        account = {
            "_id": ObjectId(), "profile": "Acc",
            "gamer_id": None, "status": "active",
            "progress_history": [], "ownership_history": [],
        }

        await pm._escalate(account)

    assert 101 in call_ids
    assert 102 in call_ids
