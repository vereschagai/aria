"""
Sprint C — Community membership gate tests.

Tests cover:
  1. Users not in the required chat are blocked by the /start handler.
  2. Members (and all statuses that aren't left/kicked/banned) pass through.
  3. Fail-open: API exceptions never block the user.
  4. Gate is skipped when required_chat_id is None (disabled).
  5. Config editor accepts negative integers (needed for group chat IDs).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# TelegramState stub (prevents current_state error in handler tests)
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
# Helpers
# ---------------------------------------------------------------------------

def _make_gate_db(required_chat_id=None):
    """Minimal DB mock for testing the gate branch of main.start()."""
    mock_db = MagicMock()
    mock_db.get_config = AsyncMock(return_value={"required_chat_id": required_chat_id})
    mock_db.is_superadmin = AsyncMock(return_value=False)
    mock_db.is_support = AsyncMock(return_value=False)
    # A known existing gamer — gate is hit before role resolution, so we put
    # the user in the gamer table to reach the gamer home branch once the gate
    # passes, rather than the newcomer branch.
    mock_db.is_gamer = AsyncMock(return_value=True)
    mock_db.get_gamer = AsyncMock(return_value={"id": 123, "username": "testuser"})
    mock_db.push_message_history = AsyncMock(return_value=None)
    mock_db.get_message_history = AsyncMock(return_value=[])
    mock_db.clean_message_history = AsyncMock(return_value=None)
    mock_db.update_gamer = AsyncMock(return_value=None)
    return mock_db


def _make_gate_message(user_id=123, username="testuser", text="/start"):
    sent = MagicMock()
    message = MagicMock()
    message.from_user.id = user_id
    message.from_user.username = username
    message.text = text
    message.answer = AsyncMock(return_value=sent)
    return message, sent


def _make_chat_member(status="member"):
    """Build a minimal chat member mock with the given status string."""
    m = MagicMock()
    m.status = status
    return m


# ---------------------------------------------------------------------------
# Gate: blocked statuses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_status", ["left", "kicked", "banned"])
async def test_gate_blocks_non_member(blocked_status):
    """Users with left/kicked/banned status must be refused with gamer_not_in_chat."""
    import main, texts

    mock_db = _make_gate_db(required_chat_id=-100123456789)
    message, _ = _make_gate_message()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})

    chat_member = _make_chat_member(status=blocked_status)

    with patch.object(main, "db", mock_db), \
         patch.object(main, "bot") as mock_bot, \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=lambda fn: fn())), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        mock_bot.get_chat_member = AsyncMock(return_value=chat_member)
        await main.start(message, state)

    mock_bot.get_chat_member.assert_called_once_with(-100123456789, 123)
    message.answer.assert_called_once()
    sent_text = message.answer.call_args[0][0]
    assert sent_text == texts.gamer_not_in_chat
    # Role resolution must NOT have run
    mock_db.is_superadmin.assert_not_called()


# ---------------------------------------------------------------------------
# Gate: allowed statuses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("allowed_status", ["member", "administrator", "creator", "restricted"])
async def test_gate_allows_member(allowed_status):
    """Users with member/admin/creator/restricted status must pass the gate."""
    import main

    mock_db = _make_gate_db(required_chat_id=-100123456789)
    message, _ = _make_gate_message()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})

    chat_member = _make_chat_member(status=allowed_status)

    with patch.object(main, "db", mock_db), \
         patch.object(main, "bot") as mock_bot, \
         patch.object(main, "TelegramState", _ts()), \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=lambda fn: fn())), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        mock_bot.get_chat_member = AsyncMock(return_value=chat_member)
        await main.start(message, state)

    mock_bot.get_chat_member.assert_called_once_with(-100123456789, 123)
    # Role resolution ran — is_superadmin was called
    mock_db.is_superadmin.assert_called_once()
    # gamer_not_in_chat was NOT sent — answer is called with something else
    import texts
    assert message.answer.called
    sent_text = message.answer.call_args[0][0]
    assert sent_text != texts.gamer_not_in_chat


# ---------------------------------------------------------------------------
# Gate: fail-open on API exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_fails_open_on_api_error():
    """Any exception from get_chat_member must be swallowed — user proceeds."""
    import main

    mock_db = _make_gate_db(required_chat_id=-100123456789)
    message, _ = _make_gate_message()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})

    with patch.object(main, "db", mock_db), \
         patch.object(main, "bot") as mock_bot, \
         patch.object(main, "TelegramState", _ts()), \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=lambda fn: fn())), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        mock_bot.get_chat_member = AsyncMock(side_effect=Exception("Telegram API error"))
        await main.start(message, state)

    # Role resolution must have continued after the exception
    mock_db.is_superadmin.assert_called_once()


# ---------------------------------------------------------------------------
# Gate: disabled when required_chat_id is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_disabled_when_no_required_chat_id():
    """When required_chat_id is None the gate is completely skipped."""
    import main

    mock_db = _make_gate_db(required_chat_id=None)
    message, _ = _make_gate_message()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})

    with patch.object(main, "db", mock_db), \
         patch.object(main, "bot") as mock_bot, \
         patch.object(main, "TelegramState", _ts()), \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=lambda fn: fn())), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        mock_bot.get_chat_member = AsyncMock()
        await main.start(message, state)

    mock_bot.get_chat_member.assert_not_called()
    mock_db.is_superadmin.assert_called_once()


# ---------------------------------------------------------------------------
# Gate: disabled when get_config returns None (empty DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_disabled_when_config_missing():
    """If get_config returns None (fresh DB), the gate should not fire."""
    import main

    mock_db = _make_gate_db()
    mock_db.get_config = AsyncMock(return_value=None)
    message, _ = _make_gate_message()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})

    with patch.object(main, "db", mock_db), \
         patch.object(main, "bot") as mock_bot, \
         patch.object(main, "TelegramState", _ts()), \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=lambda fn: fn())), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        mock_bot.get_chat_member = AsyncMock()
        await main.start(message, state)

    mock_bot.get_chat_member.assert_not_called()


# ---------------------------------------------------------------------------
# C4: Config editor accepts negative integers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_config_editor_accepts_negative_integer():
    """superadmin_edit_value_configuration must accept negative integers (group chat IDs)."""
    import main

    mock_db = MagicMock()
    mock_db.update_config = AsyncMock(return_value=None)

    message = MagicMock()
    message.text = "-100123456789"
    message.answer = AsyncMock(return_value=MagicMock())

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"field": "required_chat_id"})
    state.reset_data = AsyncMock(return_value=None)

    with patch.object(main, "db", mock_db), \
         patch.object(main, "TelegramState", _ts()), \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=lambda fn: fn())):
        await main.superadmin_edit_value_configuration(message, state)

    mock_db.update_config.assert_called_once_with("required_chat_id", -100123456789)


@pytest.mark.asyncio
async def test_config_editor_accepts_positive_integer():
    """Positive integers still work after the lstrip('-') fix."""
    import main

    mock_db = MagicMock()
    mock_db.update_config = AsyncMock(return_value=None)

    message = MagicMock()
    message.text = "42"
    message.answer = AsyncMock(return_value=MagicMock())

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"field": "max_accounts_per_gamer"})
    state.reset_data = AsyncMock(return_value=None)

    with patch.object(main, "db", mock_db), \
         patch.object(main, "TelegramState", _ts()), \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=lambda fn: fn())):
        await main.superadmin_edit_value_configuration(message, state)

    mock_db.update_config.assert_called_once_with("max_accounts_per_gamer", 42)


@pytest.mark.asyncio
async def test_config_editor_rejects_double_minus():
    """'--1' must be rejected — it looks digit-like after lstrip but int('--1') raises ValueError."""
    import main

    mock_db = MagicMock()
    mock_db.update_config = AsyncMock(return_value=None)

    message = MagicMock()
    message.text = "--1"
    message.answer = AsyncMock(return_value=MagicMock())

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"field": "required_chat_id"})

    with patch.object(main, "db", mock_db), \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=lambda fn: fn())):
        await main.superadmin_edit_value_configuration(message, state)

    mock_db.update_config.assert_not_called()


@pytest.mark.asyncio
async def test_config_editor_rejects_non_numeric():
    """Non-numeric strings must trigger the 'wrong format' reply, not update_config."""
    import main

    mock_db = MagicMock()
    mock_db.update_config = AsyncMock(return_value=None)

    message = MagicMock()
    message.text = "not-a-number"
    message.answer = AsyncMock(return_value=MagicMock())

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"field": "required_chat_id"})

    with patch.object(main, "db", mock_db), \
         patch.object(main, "safe_wrap", new=AsyncMock(side_effect=lambda fn: fn())):
        await main.superadmin_edit_value_configuration(message, state)

    mock_db.update_config.assert_not_called()
    import texts
    sent_text = message.answer.call_args[0][0]
    assert "required_chat_id" in sent_text
