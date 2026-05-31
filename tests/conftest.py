"""
Shared pytest fixtures and helpers for the aria Telegram bot test suite.

Provides:
  - mock_db:    a MagicMock standing in for MongoDb, with all async methods as AsyncMock.
  - mock_bot:   a MagicMock standing in for aiogram.Bot, send_message/forward_message as AsyncMock.
  - base_config: dict matching config.py defaults.
  - assert_valid_markdownv2: helper to verify MarkdownV2 escaping of literal content.
  - make_fake_account / make_fake_gamer: document builders for handler tests.
"""

import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch as _patch

import pytest

# ---------------------------------------------------------------------------
# Environment setup — must happen before any test file imports main.py
# ---------------------------------------------------------------------------

os.environ.setdefault("BOT_TOKEN", "123456789:AABBCCDDEEFFaabbccddeeff-1234567890")
os.environ.setdefault("ARIA_SHEET_ID", "fake_sheet_id")

# Stub packages that are absent in the test environment
for _mod in ["apiclient", "apiclient.discovery"]:
    sys.modules.setdefault(_mod, MagicMock())

for _mod in ["cryptoaddress"]:
    sys.modules.setdefault(_mod, MagicMock())

# Suppress the init() coroutine at import time (called via run_coroutine_threadsafe).
# Close the coroutine immediately so Python doesn't warn about it never being awaited.
import asyncio as _asyncio
if not getattr(_asyncio, "_test_rcts_patched", False):
    def _mock_run_coroutine_threadsafe(coro, *args, **kwargs):
        if hasattr(coro, "close"):
            coro.close()
        return MagicMock()
    _asyncio.run_coroutine_threadsafe = _mock_run_coroutine_threadsafe
    _asyncio._test_rcts_patched = True


# ---------------------------------------------------------------------------
# MarkdownV2 validation helper
# ---------------------------------------------------------------------------

MARKDOWNV2_RESERVED = set("_*[]()~`>#+-=|{}.!")

# These chars can appear bare as MarkdownV2 formatting markers (*bold*, _italic_, `code`, ~strike~).
# They do NOT need to be escaped when used as structural formatting.
_FORMATTING_MARKERS = frozenset("*_`~")

# These reserved chars must ALWAYS be escaped when appearing as literal content.
_MUST_ESCAPE = MARKDOWNV2_RESERVED - _FORMATTING_MARKERS


def assert_valid_markdownv2(text: str):
    """
    Walk text char-by-char and verify literal-content MarkdownV2 escaping.

    Backslash-escaped chars are skipped. Formatting markers (*_`~) are allowed
    bare because they're used as bold/italic/code/strikethrough delimiters.
    All other reserved chars (. + - ! ( ) [ ] = | { } > # |) must be escaped.
    """
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2  # skip escape + next char
            continue
        if ch in _MUST_ESCAPE:
            context = text[max(0, i - 30) : i + 30]
            raise AssertionError(
                f"Unescaped MarkdownV2 reserved char {ch!r} at pos {i}:\n"
                f"  ...{context}..."
            )
        i += 1


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------


def make_fake_account(
    profile="TestProfile",
    status="active",
    gamer_oid=None,
    points=1000,
    delta=100,
):
    """Generate a realistic account document for use in tests."""
    from bson import ObjectId
    from datetime import datetime

    oid = ObjectId()
    g_oid = gamer_oid or ObjectId()
    return {
        "_id": oid,
        "profile": profile,
        "login": "testlogin",
        "password": "testpass",
        "status": status,
        "gamer_id": g_oid,
        "tower": {"points": points, "rank": 50, "floor": 10},
        "proxy": {
            "host": "1.2.3.4",
            "port": "8080",
            "login": "pl",
            "password": "pp",
        },
        "progress_history": [
            {
                "synced_at": datetime(2024, 1, 1, 12, 0),
                "tower_points": points,
                "delta": delta,
                "gamer_id": g_oid,
            }
        ],
        "ownership_history": [
            {
                "gamer_id": g_oid,
                "assigned_at": datetime(2024, 1, 1),
                "released_at": None,
            }
        ],
        "last_progress_at": datetime(2024, 1, 1, 12, 0),
    }


def make_fake_gamer(user_id=12345, username="testgamer", pool_release_count=0):
    from bson import ObjectId

    return {
        "_id": ObjectId(),
        "id": user_id,
        "username": username,
        "pool_release_count": pool_release_count,
        "season_picked_up": False,
        "referral": None,
        "address": "0xTestAddress",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_config():
    return {
        "leaderboard_gap": 4,
        "leaderboard_cooldown_days": 7,
        "min_progress_points": 50,
        "max_accounts_per_gamer": 10,
        "inactivity_escalation_days": 3,
        "inactivity_day_buffer_hours": 6,
        "max_ws_tasks": 5,
        "priority_task_types": [],
    }


@pytest.fixture
def mock_db():
    """
    A MagicMock for MongoDb with all commonly-called async methods pre-wired as AsyncMock.
    Tests can override individual return values as needed.
    """
    db = MagicMock()

    # Config / meta
    db.get_config = AsyncMock(return_value=None)

    # Account helpers
    db.get_active_assigned_accounts = AsyncMock(return_value=[])
    db.get_account = AsyncMock(return_value=None)
    db.set_account_status = AsyncMock(return_value=None)
    db.get_support_users = AsyncMock(return_value=[])
    db.get_gamer_by_id = AsyncMock(return_value=None)
    db.get_gamer = AsyncMock(return_value=None)

    # WS task helpers
    db.create_task = AsyncMock(return_value=None)
    db.get_tasks = AsyncMock(return_value=[])
    db.get_task = AsyncMock(return_value=None)
    db.update_task_result = AsyncMock(return_value=None)
    db.update_task_host = AsyncMock(return_value=None)

    # Motor inner-db mock (for direct collection access in mongodb.py)
    db.db = MagicMock()
    accounts_col = MagicMock()
    db.db.accounts = accounts_col
    # find(...).to_list(None) chain
    _find_cursor = MagicMock()
    _find_cursor.to_list = AsyncMock(return_value=[])
    accounts_col.find = MagicMock(return_value=_find_cursor)
    accounts_col.insert_one = AsyncMock(return_value=None)
    accounts_col.update_one = AsyncMock(return_value=None)

    return db


@pytest.fixture
def mock_bot():
    """A MagicMock standing in for aiogram.Bot."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    bot.forward_message = AsyncMock(return_value=MagicMock())
    return bot
