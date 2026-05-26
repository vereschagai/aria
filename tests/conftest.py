"""
Shared pytest fixtures for the aria Telegram bot test suite.

Provides:
  - mock_db:    a MagicMock standing in for MongoDb, with all async methods as AsyncMock.
  - mock_bot:   a MagicMock standing in for aiogram.Bot, send_message/forward_message as AsyncMock.
  - base_config: dict matching config.py defaults.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


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
