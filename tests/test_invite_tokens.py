import pytest
import mongomock

# -- TelegramState stub (prevents current_state error in tests that call handlers) --

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


# -- async facade over synchronous mongomock ----------------------------------

class _AsyncCollection:
    """Wraps a synchronous mongomock collection so every method is awaitable."""
    def __init__(self, col):
        self._col = col

    async def find_one(self, *a, **kw):
        return self._col.find_one(*a, **kw)

    async def insert_one(self, *a, **kw):
        return self._col.insert_one(*a, **kw)

    async def count_documents(self, *a, **kw):
        return self._col.count_documents(*a, **kw)

    async def create_index(self, *a, **kw):
        return self._col.create_index(*a, **kw)


class _AsyncDb:
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return _AsyncCollection(self._db[name])


# -- helpers ------------------------------------------------------------------

def _make_mongo_db():
    """Inject mongomock client into a MongoDb instance (no real Mongo needed)."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from mongodb import MongoDb
    client = mongomock.MongoClient()
    db_instance = object.__new__(MongoDb)
    db_instance.connection = client
    db_instance.db = _AsyncDb(client["test_db"])
    return db_instance


# -- Task 1 tests: DB methods -------------------------------------------------

@pytest.mark.asyncio
async def test_ensure_invite_token_creates_new():
    db = _make_mongo_db()
    token = await db.ensure_invite_token(123456, "gamer")
    assert token["issuer_id"] == 123456
    assert token["role_type"] == "gamer"
    assert len(token["uuid"]) == 36  # UUID4 string format
    assert "created_at" in token


@pytest.mark.asyncio
async def test_ensure_invite_token_returns_existing():
    db = _make_mongo_db()
    first = await db.ensure_invite_token(123456, "gamer")
    second = await db.ensure_invite_token(123456, "gamer")
    assert first["uuid"] == second["uuid"]
    count = await db.db.invite_tokens.count_documents({"issuer_id": 123456})
    assert count == 1


@pytest.mark.asyncio
async def test_get_invite_token_by_uuid_found():
    db = _make_mongo_db()
    created = await db.ensure_invite_token(999, "support")
    found = await db.get_invite_token_by_uuid(created["uuid"])
    assert found is not None
    assert found["issuer_id"] == 999


@pytest.mark.asyncio
async def test_get_invite_token_by_uuid_not_found():
    db = _make_mongo_db()
    result = await db.get_invite_token_by_uuid("00000000-0000-0000-0000-000000000000")
    assert result is None


@pytest.mark.asyncio
async def test_ensure_invite_token_duplicate_key_race():
    """TOCTOU: insert_one raises DuplicateKeyError; method re-fetches and returns existing doc."""
    from pymongo.errors import DuplicateKeyError

    db = _make_mongo_db()
    winner = await db.ensure_invite_token(777, "gamer")

    async def raising_insert(doc):
        raise DuplicateKeyError("duplicate", code=11000)

    db.db.invite_tokens.insert_one = raising_insert

    result = await db.ensure_invite_token(777, "gamer")
    assert result["uuid"] == winner["uuid"]
    assert result["issuer_id"] == 777


# -- Task 5 tests: /start UUID referral ---------------------------------------
#
# These tests call the actual main.start() handler so that regressions in the
# handler body are caught. The newcomer branch is exercised (is_gamer -> False
# for the new user). The issuer is a known gamer so the referral is not zeroed
# by the self-referral / unknown-user guard.

def _make_start_db(issuer_id=555, token_doc=None):
    """DB mock configured for the newcomer branch of main.start()."""
    from unittest.mock import AsyncMock, MagicMock

    mock_db = MagicMock()

    async def is_gamer(query):
        return query.get("id") == issuer_id  # True only for the issuer

    mock_db.is_superadmin = AsyncMock(return_value=False)
    mock_db.is_support = AsyncMock(return_value=False)
    mock_db.is_gamer = is_gamer
    mock_db.get_config = AsyncMock(return_value={"required_chat_id": None})
    mock_db.get_invite_token_by_uuid = AsyncMock(return_value=token_doc)
    mock_db.add_gamer = AsyncMock(return_value=None)
    mock_db.update_gamer = AsyncMock(return_value=None)
    mock_db.get_gamer_accounts = AsyncMock(return_value=[])
    mock_db.push_message_history = AsyncMock(return_value=None)
    mock_db.get_message_history = AsyncMock(return_value=[])
    mock_db.clean_message_history = AsyncMock(return_value=None)
    return mock_db


def _make_start_message(user_id=777, username="newbie", text="/start abc-uuid-123"):
    from unittest.mock import MagicMock, AsyncMock
    sent = MagicMock()
    message = MagicMock()
    message.from_user.id = user_id
    message.from_user.username = username
    message.text = text
    message.answer = AsyncMock(return_value=sent)
    return message, sent


@pytest.mark.asyncio
async def test_start_handler_resolves_uuid_referral():
    """Valid UUID in ?start= -> get_invite_token_by_uuid called; add_gamer gets referral."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock

    fake_token = {"uuid": "abc-uuid-123", "issuer_id": 555, "role_type": "gamer"}
    mock_db = _make_start_db(issuer_id=555, token_doc=fake_token)
    message, _ = _make_start_message()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock(return_value=None)
    state.set_data = AsyncMock(return_value=None)

    with patch.object(main, "db", mock_db), \
         patch.object(main, "TelegramState", _ts()), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        await main.start(message, state)

    mock_db.get_invite_token_by_uuid.assert_called_once_with("abc-uuid-123")
    mock_db.add_gamer.assert_called_once()
    _, _username, call_referral = mock_db.add_gamer.call_args[0]
    assert call_referral == 555


@pytest.mark.asyncio
async def test_start_handler_unknown_uuid_gives_no_referral():
    """Unknown UUID in ?start= -> newcomer is NOT registered (invite-only gate fires)."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock

    mock_db = _make_start_db(token_doc=None)
    message, _ = _make_start_message(text="/start 00000000-0000-0000-0000-000000000000")
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock(return_value=None)
    state.set_data = AsyncMock(return_value=None)

    with patch.object(main, "db", mock_db), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        await main.start(message, state)

    mock_db.get_invite_token_by_uuid.assert_called_once_with("00000000-0000-0000-0000-000000000000")
    mock_db.add_gamer.assert_not_called()


# -- Task 6 tests: add_support and add_superadmin create tokens ---------------

@pytest.mark.asyncio
async def test_add_support_handler_creates_invite_token():
    """admin_added (support branch) calls ensure_invite_token after add_support."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock

    mock_db = MagicMock()
    mock_db.is_support = AsyncMock(return_value=False)
    mock_db.add_support = AsyncMock(return_value=None)
    mock_db.ensure_invite_token = AsyncMock(return_value={"uuid": "tok-xyz", "issuer_id": 888})

    contact = MagicMock()
    contact.user_id = 888
    contact.full_name = "Support User"

    message = MagicMock()
    message.contact = contact
    message.answer = AsyncMock(return_value=MagicMock())

    state = MagicMock()
    state.get_state = AsyncMock(return_value="TelegramState:admin_add_support")

    with patch.object(main, "db", mock_db), \
         patch.object(main, "TelegramState", _ts()):
        await main.admin_added(message, state)

    mock_db.add_support.assert_called_once_with(contact)
    mock_db.ensure_invite_token.assert_called_once_with(888, "support")


@pytest.mark.asyncio
async def test_add_superadmin_handler_creates_invite_token():
    """admin_added (superadmin branch) calls ensure_invite_token after add_superadmin."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock

    mock_db = MagicMock()
    mock_db.is_superadmin = AsyncMock(return_value=False)
    mock_db.add_superadmin = AsyncMock(return_value=None)
    mock_db.ensure_invite_token = AsyncMock(return_value={"uuid": "tok-sa", "issuer_id": 999})

    contact = MagicMock()
    contact.user_id = 999
    contact.full_name = "New SA"

    message = MagicMock()
    message.contact = contact
    message.answer = AsyncMock(return_value=MagicMock())

    state = MagicMock()
    state.get_state = AsyncMock(return_value="TelegramState:superadmin_add_admin")

    with patch.object(main, "db", mock_db), \
         patch.object(main, "TelegramState", _ts()):
        await main.admin_added(message, state)

    mock_db.add_superadmin.assert_called_once()
    mock_db.ensure_invite_token.assert_called_once_with(999, "superadmin")


# -- Task 7 tests: invite link handlers ---------------------------------------
#
# _spy_safe_wrap: asserts safe_wrap receives a CALLABLE (lambda), not a bare
# coroutine. Passes the callable through so message.answer actually executes.
# Patching strategy: handlers use the module-level safe_wrap alias (bound to
# utils.safe_wrap at import time), so patch main.safe_wrap directly.

async def _spy_safe_wrap(fn):
    assert callable(fn), (
        f"safe_wrap must receive a callable (lambda), got {type(fn).__name__}. "
        "Use: await safe_wrap(lambda: message.answer(...))"
    )
    return await fn()


def _make_invite_mocks(user_id, fake_token):
    from unittest.mock import AsyncMock, MagicMock
    mock_db = MagicMock()
    mock_db.ensure_invite_token = AsyncMock(return_value=fake_token)
    sent_msg = MagicMock()
    message = MagicMock()
    message.from_user.id = user_id
    message.answer = AsyncMock(return_value=sent_msg)
    return mock_db, message, sent_msg


@pytest.mark.asyncio
async def test_gamer_invite_link_handler_safe_wrap_receives_callable():
    """safe_wrap must receive a lambda (not a bare coroutine), and preview must be suppressed."""
    import main
    from unittest.mock import patch, AsyncMock

    fake_token = {"uuid": "gamer-uuid-123", "issuer_id": 777, "role_type": "gamer"}
    mock_db, message, _ = _make_invite_mocks(777, fake_token)

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"), \
         patch.object(main, "safe_wrap", _spy_safe_wrap), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        await main.gamer_invite_link(message)

    mock_db.ensure_invite_token.assert_called_once_with(777, "gamer")
    sent_text = message.answer.call_args[0][0]
    assert "gamer-uuid-123" in sent_text
    assert "aria_test_bot" in sent_text
    assert message.answer.call_args[1].get("disable_web_page_preview") is True


@pytest.mark.asyncio
async def test_gamer_invite_link_handler_performs_message_cleanup():
    """Handler must track incoming, clean old messages, send, track outgoing."""
    import main
    from unittest.mock import patch, AsyncMock

    fake_token = {"uuid": "gamer-uuid-123", "issuer_id": 777, "role_type": "gamer"}
    mock_db, message, sent_msg = _make_invite_mocks(777, fake_token)
    mock_add = AsyncMock()
    mock_clean = AsyncMock()

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"), \
         patch.object(main, "safe_wrap", _spy_safe_wrap), \
         patch("utils.add_message_history", mock_add), \
         patch("utils.clean_messages", mock_clean):
        await main.gamer_invite_link(message)

    mock_clean.assert_called_once()
    assert mock_add.call_count == 2
    second_call_msg = mock_add.call_args_list[1][0][1]
    assert second_call_msg is sent_msg


@pytest.mark.asyncio
async def test_superadmin_invite_link_handler_safe_wrap_receives_callable():
    """safe_wrap must receive a lambda (not a bare coroutine), and preview must be suppressed."""
    import main
    from unittest.mock import patch, AsyncMock

    fake_token = {"uuid": "sa-uuid-456", "issuer_id": 1, "role_type": "superadmin"}
    mock_db, message, _ = _make_invite_mocks(1, fake_token)

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"), \
         patch.object(main, "safe_wrap", _spy_safe_wrap), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        await main.superadmin_invite_link(message)

    mock_db.ensure_invite_token.assert_called_once_with(1, "superadmin")
    sent_text = message.answer.call_args[0][0]
    assert "sa-uuid-456" in sent_text
    assert message.answer.call_args[1].get("disable_web_page_preview") is True


@pytest.mark.asyncio
async def test_superadmin_invite_link_handler_performs_message_cleanup():
    """Handler must track incoming, clean old messages, send, track outgoing."""
    import main
    from unittest.mock import patch, AsyncMock

    fake_token = {"uuid": "sa-uuid-456", "issuer_id": 1, "role_type": "superadmin"}
    mock_db, message, sent_msg = _make_invite_mocks(1, fake_token)
    mock_add = AsyncMock()
    mock_clean = AsyncMock()

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"), \
         patch.object(main, "safe_wrap", _spy_safe_wrap), \
         patch("utils.add_message_history", mock_add), \
         patch("utils.clean_messages", mock_clean):
        await main.superadmin_invite_link(message)

    mock_clean.assert_called_once()
    assert mock_add.call_count == 2
    second_call_msg = mock_add.call_args_list[1][0][1]
    assert second_call_msg is sent_msg


@pytest.mark.asyncio
async def test_support_invite_link_handler_safe_wrap_receives_callable():
    """safe_wrap must receive a lambda (not a bare coroutine), and preview must be suppressed."""
    import main
    from unittest.mock import patch, AsyncMock

    fake_token = {"uuid": "sup-uuid-789", "issuer_id": 444, "role_type": "support"}
    mock_db, message, _ = _make_invite_mocks(444, fake_token)

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"), \
         patch.object(main, "safe_wrap", _spy_safe_wrap), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        await main.support_invite_link(message)

    mock_db.ensure_invite_token.assert_called_once_with(444, "support")
    sent_text = message.answer.call_args[0][0]
    assert "sup-uuid-789" in sent_text
    assert message.answer.call_args[1].get("disable_web_page_preview") is True


@pytest.mark.asyncio
async def test_support_invite_link_handler_performs_message_cleanup():
    """Handler must track incoming, clean old messages, send, track outgoing."""
    import main
    from unittest.mock import patch, AsyncMock

    fake_token = {"uuid": "sup-uuid-789", "issuer_id": 444, "role_type": "support"}
    mock_db, message, sent_msg = _make_invite_mocks(444, fake_token)
    mock_add = AsyncMock()
    mock_clean = AsyncMock()

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"), \
         patch.object(main, "safe_wrap", _spy_safe_wrap), \
         patch("utils.add_message_history", mock_add), \
         patch("utils.clean_messages", mock_clean):
        await main.support_invite_link(message)

    mock_clean.assert_called_once()
    assert mock_add.call_count == 2
    second_call_msg = mock_add.call_args_list[1][0][1]
    assert second_call_msg is sent_msg


# -- gamer_referral_link handler (buttons.referral) uses UUID token -----------

@pytest.mark.asyncio
async def test_gamer_referral_link_handler_uses_uuid_token():
    """buttons.referral handler must use ensure_invite_token (not raw user_id) for the link."""
    import main
    from unittest.mock import patch, AsyncMock, MagicMock

    fake_token = {"uuid": "referral-uuid-abc", "issuer_id": 777, "role_type": "gamer"}
    mock_db = MagicMock()
    mock_db.ensure_invite_token = AsyncMock(return_value=fake_token)

    sent_msg = MagicMock()
    message = MagicMock()
    message.from_user.id = 777
    message.answer = AsyncMock(return_value=sent_msg)

    state = MagicMock()
    state.set = AsyncMock(return_value=None)

    with patch.object(main, "db", mock_db), \
         patch.object(main, "BOT_USERNAME", "aria_test_bot"), \
         patch.object(main, "TelegramState", _ts()), \
         patch("utils.add_message_history", AsyncMock()), \
         patch("utils.clean_messages", AsyncMock()):
        await main.gamer_referral_link(message, state)

    mock_db.ensure_invite_token.assert_called_once_with(777, "gamer")
    sent_text = message.answer.call_args[0][0]
    # The UUID is passed through utils.escape() which escapes '-' to '\-'
    assert "referral\\-uuid\\-abc" in sent_text
    # Must NOT contain the raw integer user_id as the start parameter
    assert "?start=777" not in sent_text
