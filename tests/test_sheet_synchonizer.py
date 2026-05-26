"""
Tests for GoogleSheetSynchonizer (sheet_synchonizer.py).

BRD requirement covered: Google Sheets sync that parses tower data,
enforces Option-C (never writes gamer_id), and gates on Active/Proxy columns.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, AsyncMock
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sheet_row(
    profile="ACC1",
    login="login1",
    password="pass1",
    proxy="1.2.3.4:3128:user:secret",
    old_gamer="@old",
    active="ACC1",     # set to "#N/A" to mark inactive
    gamer="@gamer",    # ignored by synchonizer (Option C)
    tp_start="500;3;2",
    current_points=None,  # if given, appended as the "last daily column"
):
    """Build a sheet row (list of strings) with sane defaults."""
    row = [profile, login, password, proxy, old_gamer, active, gamer, tp_start]
    if current_points is not None:
        row.append(current_points)
    return row


# ---------------------------------------------------------------------------
# __parse_tower  (accessed via Python name-mangling)
# ---------------------------------------------------------------------------

def _parse_tower(raw):
    """Invoke the private static method via name mangling."""
    from sheet_synchonizer import GoogleSheetSynchonizer
    return GoogleSheetSynchonizer._GoogleSheetSynchonizer__parse_tower(raw)


def test_parse_tower_valid():
    """Case 1: valid format '1000;5;3' → {points:1000, rank:5, floor:3}."""
    result = _parse_tower("1000;5;3")
    assert result == {"points": 1000, "rank": 5, "floor": 3}


def test_parse_tower_nan_values():
    """Case 2: 'NaN;NaN;NaN' → all zeros."""
    result = _parse_tower("NaN;NaN;NaN")
    assert result == {"points": 0, "rank": 0, "floor": 0}


def test_parse_tower_empty_string():
    """Case 3: empty string → all zeros."""
    result = _parse_tower("")
    assert result == {"points": 0, "rank": 0, "floor": 0}


def test_parse_tower_partial():
    """Case 4: '500;2' — only two parts → floor defaults to 0."""
    result = _parse_tower("500;2")
    assert result["points"] == 500
    assert result["rank"] == 2
    assert result["floor"] == 0


# ---------------------------------------------------------------------------
# grab_accounts — row-level guards
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grab_accounts_skips_inactive_active_column(mock_db, base_config):
    """Case 5: row with Active='#N/A' is skipped entirely — no insert."""
    from sheet_synchonizer import GoogleSheetSynchonizer

    row = _make_sheet_row(active="#N/A", current_points="1000;5;3")
    mock_api = MagicMock()
    mock_api.get_accounts = AsyncMock(return_value=[row])
    mock_db.get_config = AsyncMock(return_value=base_config)
    mock_db.get_account = AsyncMock(return_value=None)

    syncer = GoogleSheetSynchonizer(mock_db, mock_api)
    await syncer.grab_accounts()

    mock_db.db.accounts.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_grab_accounts_skips_no_proxy(mock_db, base_config):
    """Case 6: row with Proxy='#N/A' is skipped entirely — no insert."""
    from sheet_synchonizer import GoogleSheetSynchonizer

    row = _make_sheet_row(proxy="#N/A", current_points="1000;5;3")
    mock_api = MagicMock()
    mock_api.get_accounts = AsyncMock(return_value=[row])
    mock_db.get_config = AsyncMock(return_value=base_config)
    mock_db.get_account = AsyncMock(return_value=None)

    syncer = GoogleSheetSynchonizer(mock_db, mock_api)
    await syncer.grab_accounts()

    mock_db.db.accounts.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_grab_accounts_skips_short_rows(mock_db, base_config):
    """Case 7: row with fewer than 6 columns is skipped."""
    from sheet_synchonizer import GoogleSheetSynchonizer

    short_row = ["ACC1", "login", "pass", "proxy"]  # only 4 columns
    mock_api = MagicMock()
    mock_api.get_accounts = AsyncMock(return_value=[short_row])
    mock_db.get_config = AsyncMock(return_value=base_config)
    mock_db.get_account = AsyncMock(return_value=None)

    syncer = GoogleSheetSynchonizer(mock_db, mock_api)
    await syncer.grab_accounts()

    mock_db.db.accounts.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_grab_accounts_upserts_basic_fields(mock_db, base_config):
    """Case 8: valid new row → insert_one called with profile/login/password/proxy."""
    from sheet_synchonizer import GoogleSheetSynchonizer

    row = _make_sheet_row(
        profile="MyAcc",
        login="mylogin",
        password="mypass",
        proxy="10.0.0.1:8080:proxyuser:proxypass",
        tp_start="200;2;1",
        current_points="300;3;2",
    )

    mock_api = MagicMock()
    mock_api.get_accounts = AsyncMock(return_value=[row])
    mock_db.get_config = AsyncMock(return_value=base_config)
    mock_db.get_account = AsyncMock(return_value=None)  # brand-new account

    syncer = GoogleSheetSynchonizer(mock_db, mock_api)
    await syncer.grab_accounts()

    mock_db.db.accounts.insert_one.assert_called_once()
    inserted = mock_db.db.accounts.insert_one.call_args[0][0]
    assert inserted["profile"] == "MyAcc"
    assert inserted["login"] == "mylogin"
    assert inserted["password"] == "mypass"
    assert inserted["proxy"]["host"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_grab_accounts_never_writes_gamer_id_on_update(mock_db, base_config):
    """Case 9: existing-account update path must never include gamer_id in $set."""
    from sheet_synchonizer import GoogleSheetSynchonizer

    existing_gamer_oid = ObjectId()
    existing = {
        "_id": ObjectId(),
        "profile": "MyAcc",
        "gamer_id": existing_gamer_oid,
        "status": "active",
        "progress_history": [
            {
                "synced_at": None,
                "tower_points": 100,
                "delta": 100,
                "gamer_id": existing_gamer_oid,
            }
        ],
    }

    row = _make_sheet_row(profile="MyAcc", current_points="200;2;1")

    mock_api = MagicMock()
    mock_api.get_accounts = AsyncMock(return_value=[row])
    mock_db.get_config = AsyncMock(return_value=base_config)
    mock_db.get_account = AsyncMock(return_value=existing)

    syncer = GoogleSheetSynchonizer(mock_db, mock_api)
    await syncer.grab_accounts()

    mock_db.db.accounts.update_one.assert_called_once()
    _, update_doc = mock_db.db.accounts.update_one.call_args[0]
    set_fields = update_doc.get("$set", {})
    assert "gamer_id" not in set_fields, "gamer_id must NEVER be written by the synchonizer"


@pytest.mark.asyncio
async def test_grab_accounts_new_account_status_released(mock_db, base_config):
    """Case 10: brand-new account gets status='released' on first insert."""
    from sheet_synchonizer import GoogleSheetSynchonizer

    row = _make_sheet_row(
        profile="FreshAcc",
        tp_start="0;0;0",
        current_points="50;1;1",
    )

    mock_api = MagicMock()
    mock_api.get_accounts = AsyncMock(return_value=[row])
    mock_db.get_config = AsyncMock(return_value=base_config)
    mock_db.get_account = AsyncMock(return_value=None)

    syncer = GoogleSheetSynchonizer(mock_db, mock_api)
    await syncer.grab_accounts()

    mock_db.db.accounts.insert_one.assert_called_once()
    inserted = mock_db.db.accounts.insert_one.call_args[0][0]
    assert inserted["status"] == "released"
