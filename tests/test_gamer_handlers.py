"""
Gamer flow handler tests — 18 tests covering:
  pickup flow, release prompt, release select, support decisions, account screen.

Handlers are imported from main.py (module-level globals db/bot/synchonizer are patched
per-test via patch.object). TelegramState class-level .set() calls are stubbed with
_AsyncState so they can be awaited without a live dispatcher.
"""

import sys
import os
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from bson import ObjectId
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main  # safe — conftest.py set up env vars and stubs before collection


# ---------------------------------------------------------------------------
# TelegramState stub
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
# Per-test DB / bot / message helpers
# ---------------------------------------------------------------------------


def _make_db(gamer=None, **overrides):
    """Full MongoDb mock with all handler-required async methods."""
    if gamer is None:
        gamer = {
            "_id": ObjectId(),
            "id": 12345,
            "username": "testgamer",
            "pool_release_count": 0,
            "referral": None,
            "address": "0xTestAddress",
        }
    db = MagicMock()
    db.get_gamer = AsyncMock(return_value=gamer)
    db.get_config = AsyncMock(
        return_value={
            "max_accounts_per_gamer": 10,
            "min_progress_points": 50,
            "support_handle": "@testsupp",
        }
    )
    db.get_gamer_accounts = AsyncMock(return_value=[])
    db.get_support_users = AsyncMock(return_value=[])
    db.is_support = AsyncMock(return_value=False)
    db.is_superadmin = AsyncMock(return_value=False)
    db.check_assignment_eligibility = AsyncMock(return_value=(True, "ok"))
    db.pickup_account = AsyncMock(return_value=None)
    db.mark_gamer_season_active = AsyncMock(return_value=None)
    db.request_account_release = AsyncMock(return_value=MagicMock(modified_count=1))
    db.get_account_by_object_id = AsyncMock(return_value=None)
    db.get_account = AsyncMock(return_value=None)
    db.add_release_block = AsyncMock(return_value=None)
    db.increment_pool_release_count = AsyncMock(return_value=1)
    db.release_account = AsyncMock(return_value=None)
    db.finish_account = AsyncMock(return_value=None)
    db.set_account_status = AsyncMock(return_value=None)
    db.get_gamer_by_id = AsyncMock(return_value=None)
    db.get_gamer_season_points = AsyncMock(return_value=0)
    db.count_gamers = AsyncMock(return_value=0)
    db.push_message_history = AsyncMock(return_value=None)
    db.get_message_history = AsyncMock(return_value=[])
    db.clean_message_history = AsyncMock(return_value=None)
    for key, val in overrides.items():
        setattr(db, key, val)
    return db, gamer


def _make_bot():
    bot = MagicMock()
    sent = MagicMock(chat=MagicMock(id=12345), message_id=999)
    bot.send_message = AsyncMock(return_value=sent)
    bot.delete_message = AsyncMock(return_value=True)
    return bot


def _make_msg(user_id=12345):
    msg = MagicMock()
    msg.from_user = MagicMock(id=user_id, username="testgamer")
    msg.chat = MagicMock(id=user_id)
    msg.message_id = 1
    msg.text = "test"
    sent = MagicMock(chat=MagicMock(id=user_id), message_id=2)
    msg.answer = AsyncMock(return_value=sent)
    return msg


def _make_cb(data, user_id=12345):
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id)
    cb.answer = AsyncMock(return_value=None)
    return cb


def _make_synchonizer():
    s = MagicMock()
    s.sync_single_account = AsyncMock(return_value=None)
    return s


# ---------------------------------------------------------------------------
# Pickup flow (tests 1–6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pickup_ineligible_slot_full():
    """Ineligible (slot full) → message sent, pickup_account NOT called."""
    db, _ = _make_db(
        check_assignment_eligibility=AsyncMock(
            return_value=(False, "Достигнут лимит аккаунтов (5)")
        )
    )
    bot = _make_bot()
    msg = _make_msg()
    state = MagicMock()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_pickup_account(msg, state)

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "Достигнут лимит аккаунтов" in text
    db.pickup_account.assert_not_called()


@pytest.mark.asyncio
async def test_pickup_ineligible_progress_below_min():
    """Ineligible (bad progress) → message sent, pickup_account NOT called."""
    db, _ = _make_db(
        check_assignment_eligibility=AsyncMock(
            return_value=(False, "acc1 — недостаточно прогресса (нужно 50+ очков башни)")
        )
    )
    bot = _make_bot()
    msg = _make_msg()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_pickup_account(msg, MagicMock())

    text = msg.answer.call_args[0][0]
    assert "недостаточно прогресса" in text
    db.pickup_account.assert_not_called()


@pytest.mark.asyncio
async def test_pickup_ineligible_banned():
    """Banned gamer (pool_release_count >= 5) gets ineligible message, no pickup."""
    ban_reason = "Вы освободили слишком много аккаунтов. Взять новый нельзя."
    db, _ = _make_db(
        check_assignment_eligibility=AsyncMock(return_value=(False, ban_reason))
    )
    bot = _make_bot()
    msg = _make_msg()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_pickup_account(msg, MagicMock())

    text = msg.answer.call_args[0][0]
    assert "освободили" in text
    db.pickup_account.assert_not_called()


@pytest.mark.asyncio
async def test_pickup_no_accounts_available():
    """Eligible gamer but pool is empty → no-accounts message sent."""
    db, _ = _make_db(
        check_assignment_eligibility=AsyncMock(return_value=(True, "ok")),
        pickup_account=AsyncMock(return_value=None),
    )
    bot = _make_bot()
    msg = _make_msg()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_pickup_account(msg, MagicMock())

    text = msg.answer.call_args[0][0]
    assert "нет свободных" in text


@pytest.mark.asyncio
async def test_pickup_success_sends_credentials():
    """Successful pickup → success message sent, mark_gamer_season_active called once."""
    account_oid = ObjectId()
    account = {
        "_id": account_oid,
        "profile": "MyAccount",
        "login": "user123",
        "password": "pass456",
    }
    db, _ = _make_db(
        check_assignment_eligibility=AsyncMock(return_value=(True, "ok")),
        pickup_account=AsyncMock(return_value=account),
        mark_gamer_season_active=AsyncMock(return_value=None),
    )
    bot = _make_bot()
    msg = _make_msg()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_pickup_account(msg, MagicMock())

    msg.answer.assert_called_once()
    db.mark_gamer_season_active.assert_called_once()


@pytest.mark.asyncio
async def test_pickup_success_message_contains_profile_and_login():
    """Success message text contains the profile name and login."""
    account = {
        "_id": ObjectId(),
        "profile": "GoldAccount",
        "login": "golduser",
        "password": "goldpass",
    }
    db, _ = _make_db(
        check_assignment_eligibility=AsyncMock(return_value=(True, "ok")),
        pickup_account=AsyncMock(return_value=account),
        mark_gamer_season_active=AsyncMock(return_value=None),
    )
    bot = _make_bot()
    msg = _make_msg()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_pickup_account(msg, MagicMock())

    text = msg.answer.call_args[0][0]
    assert "GoldAccount" in text
    assert "golduser" in text


# ---------------------------------------------------------------------------
# Release prompt (tests 7–8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_prompt_no_active_accounts():
    """All accounts are non-active → no-accounts message sent with start markup."""
    from tests.conftest import make_fake_gamer, make_fake_account

    gamer_doc = make_fake_gamer()
    escalated = make_fake_account(status="escalated", gamer_oid=gamer_doc["_id"])
    pending = make_fake_account(status="pending_release", gamer_oid=gamer_doc["_id"])

    db, _ = _make_db(
        gamer=gamer_doc,
        get_gamer_accounts=AsyncMock(return_value=[escalated, pending]),
    )
    bot = _make_bot()
    msg = _make_msg()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_release_account_prompt(msg, MagicMock())

    text = msg.answer.call_args[0][0]
    assert "Нет активных" in text


@pytest.mark.asyncio
async def test_release_prompt_builds_inline_keyboard():
    """3 active accounts → inline keyboard has 3 account buttons + 1 back = 4 total."""
    from tests.conftest import make_fake_gamer, make_fake_account

    gamer_doc = make_fake_gamer()
    accounts = [
        make_fake_account(profile=f"Acc{i}", status="active", gamer_oid=gamer_doc["_id"])
        for i in range(3)
    ]

    db, _ = _make_db(
        gamer=gamer_doc,
        get_gamer_accounts=AsyncMock(return_value=accounts),
    )
    bot = _make_bot()
    msg = _make_msg()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_release_account_prompt(msg, MagicMock())

    kwargs = msg.answer.call_args[1]
    markup = kwargs["reply_markup"]
    all_buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(all_buttons) == 4  # 3 accounts + 1 back


# ---------------------------------------------------------------------------
# Release select (tests 9–12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_select_account_already_changed_status():
    """request_account_release returns modified_count=0 → early return, no notification sent."""
    gamer_doc = {
        "_id": ObjectId(),
        "id": 12345,
        "username": "testgamer",
        "pool_release_count": 0,
    }
    account_oid = ObjectId()
    account = {"_id": account_oid, "profile": "TestAcc", "status": "active", "gamer_id": gamer_doc["_id"]}

    db, _ = _make_db(
        gamer=gamer_doc,
        get_account_by_object_id=AsyncMock(return_value=account),
        request_account_release=AsyncMock(return_value=MagicMock(modified_count=0)),
    )
    bot = _make_bot()
    cb = _make_cb(f"release_select:{account_oid}")

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ), patch.object(main, "synchonizer", _make_synchonizer()):
        await main.gamer_release_account_select(cb, MagicMock())

    cb.answer.assert_called_once()
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_release_select_notifies_all_support_users():
    """3 support users → bot.send_message called 3 times (support) + 1 (gamer) = 4."""
    gamer_doc = {
        "_id": ObjectId(),
        "id": 12345,
        "username": "testgamer",
        "pool_release_count": 0,
    }
    account_oid = ObjectId()
    account = {
        "_id": account_oid,
        "profile": "TestAcc",
        "status": "active",
        "gamer_id": gamer_doc["_id"],
        "progress_history": [],
    }
    support_users = [{"id": 101}, {"id": 102}, {"id": 103}]

    db, _ = _make_db(
        gamer=gamer_doc,
        get_account_by_object_id=AsyncMock(return_value=account),
        get_account=AsyncMock(return_value={**account, "progress_history": []}),
        request_account_release=AsyncMock(return_value=MagicMock(modified_count=1)),
        get_support_users=AsyncMock(return_value=support_users),
    )
    bot = _make_bot()
    cb = _make_cb(f"release_select:{account_oid}")

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ), patch.object(main, "synchonizer", _make_synchonizer()):
        await main.gamer_release_account_select(cb, MagicMock())

    assert bot.send_message.call_count == 4


@pytest.mark.asyncio
async def test_release_select_progress_filtered_by_gamer():
    """Support notification includes only gamer-owned history entries, not other-gamer entries."""
    gamer_doc = {
        "_id": ObjectId(),
        "id": 12345,
        "username": "testgamer",
        "pool_release_count": 0,
    }
    other_oid = ObjectId()
    account_oid = ObjectId()

    gamer_entries = [
        {
            "synced_at": datetime(2024, 1, i + 1, 12, 0),
            "tower_points": 10000 + i,
            "delta": 100,
            "gamer_id": gamer_doc["_id"],
        }
        for i in range(3)
    ]
    other_entries = [
        {
            "synced_at": datetime(2024, 1, i + 1, 8, 0),
            "tower_points": 99900 + i,
            "delta": 50,
            "gamer_id": other_oid,
        }
        for i in range(5)
    ]

    full_history = other_entries + gamer_entries
    account = {
        "_id": account_oid,
        "profile": "TestAcc",
        "status": "active",
        "gamer_id": gamer_doc["_id"],
        "progress_history": full_history,
    }

    db, _ = _make_db(
        gamer=gamer_doc,
        get_account_by_object_id=AsyncMock(return_value=account),
        get_account=AsyncMock(return_value=account),
        request_account_release=AsyncMock(return_value=MagicMock(modified_count=1)),
        get_support_users=AsyncMock(return_value=[{"id": 200}]),
    )
    bot = _make_bot()
    cb = _make_cb(f"release_select:{account_oid}")

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ), patch.object(main, "synchonizer", _make_synchonizer()):
        await main.gamer_release_account_select(cb, MagicMock())

    # Find the support notification call (first bot.send_message call with support user's id)
    support_calls = [c for c in bot.send_message.call_args_list if c[0][0] == 200]
    assert len(support_calls) == 1
    notification_text = support_calls[0][0][1]

    # Gamer tower_points (10000, 10001, 10002) must appear
    assert "10000" in notification_text or "10001" in notification_text or "10002" in notification_text
    # Other-gamer tower_points must not appear
    assert "99900" not in notification_text
    assert "99901" not in notification_text


@pytest.mark.asyncio
async def test_release_select_callback_answer_called():
    """callback_query.answer('') is called (MUST be first in aiogram callbacks)."""
    gamer_doc = {
        "_id": ObjectId(),
        "id": 12345,
        "username": "testgamer",
        "pool_release_count": 0,
    }
    account_oid = ObjectId()
    account = {
        "_id": account_oid,
        "profile": "TestAcc",
        "status": "active",
        "gamer_id": gamer_doc["_id"],
        "progress_history": [],
    }

    db, _ = _make_db(
        gamer=gamer_doc,
        get_account_by_object_id=AsyncMock(return_value=account),
        get_account=AsyncMock(return_value={**account}),
        request_account_release=AsyncMock(return_value=MagicMock(modified_count=1)),
        get_support_users=AsyncMock(return_value=[]),
    )
    bot = _make_bot()
    cb = _make_cb(f"release_select:{account_oid}")

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ), patch.object(main, "synchonizer", _make_synchonizer()):
        await main.gamer_release_account_select(cb, MagicMock())

    cb.answer.assert_called()


# ---------------------------------------------------------------------------
# Support decisions (tests 13–16)
# ---------------------------------------------------------------------------


def _make_support_account(status="pending_release"):
    gamer_oid = ObjectId()
    account_oid = ObjectId()
    return (
        {
            "_id": account_oid,
            "profile": "SupportTestAcc",
            "status": status,
            "gamer_id": gamer_oid,
            "tower": {"points": 500},
            "release_request": {"type": "on_demand"},
        },
        gamer_oid,
        account_oid,
    )


@pytest.mark.asyncio
async def test_support_pool_decision_calls_add_block_and_release():
    """release_pool decision → add_release_block and release_account both called."""
    account, gamer_oid, account_oid = _make_support_account()
    gamer = {"_id": gamer_oid, "id": 55555, "username": "gamer"}

    db, _ = _make_db(
        is_support=AsyncMock(return_value=True),
        get_account_by_object_id=AsyncMock(return_value=account),
        get_gamer_by_id=AsyncMock(return_value=gamer),
        increment_pool_release_count=AsyncMock(return_value=1),
    )
    bot = _make_bot()
    cb = _make_cb(f"release_pool:{account_oid}", user_id=99)

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.support_release_decision(cb, )

    db.add_release_block.assert_called_once()
    db.release_account.assert_called_once()


@pytest.mark.asyncio
async def test_support_pool_decision_sends_ban_at_5():
    """When new pool_release_count reaches 5, ban message sent to gamer before pool-approved."""
    account, gamer_oid, account_oid = _make_support_account()
    gamer = {"_id": gamer_oid, "id": 55555, "username": "gamer"}

    db, _ = _make_db(
        is_support=AsyncMock(return_value=True),
        get_account_by_object_id=AsyncMock(return_value=account),
        get_gamer_by_id=AsyncMock(return_value=gamer),
        increment_pool_release_count=AsyncMock(return_value=5),
    )
    bot = _make_bot()
    cb = _make_cb(f"release_pool:{account_oid}", user_id=99)

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.support_release_decision(cb, )

    gamer_calls = [c for c in bot.send_message.call_args_list if c[0][0] == 55555]
    assert len(gamer_calls) >= 2
    # Ban message must be sent before pool-approved
    ban_call_idx = next(
        i for i, c in enumerate(gamer_calls) if "освободили" in c[0][1]
    )
    pool_call_idx = next(
        i for i, c in enumerate(gamer_calls) if "пул" in c[0][1]
    )
    assert ban_call_idx < pool_call_idx


@pytest.mark.asyncio
async def test_support_finish_decision_calls_finish_account():
    """release_finish decision → finish_account called, gamer notified."""
    account, gamer_oid, account_oid = _make_support_account()
    gamer = {"_id": gamer_oid, "id": 55555, "username": "gamer"}

    db, _ = _make_db(
        is_support=AsyncMock(return_value=True),
        get_account_by_object_id=AsyncMock(return_value=account),
        get_gamer_by_id=AsyncMock(return_value=gamer),
    )
    bot = _make_bot()
    cb = _make_cb(f"release_finish:{account_oid}", user_id=99)

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.support_release_decision(cb, )

    db.finish_account.assert_called_once()
    gamer_calls = [c for c in bot.send_message.call_args_list if c[0][0] == 55555]
    assert len(gamer_calls) == 1
    assert "закрыт" in gamer_calls[0][0][1]


@pytest.mark.asyncio
async def test_support_deny_decision_restores_active():
    """release_deny decision → set_account_status('active') called, gamer notified."""
    account, gamer_oid, account_oid = _make_support_account()
    gamer = {"_id": gamer_oid, "id": 55555, "username": "gamer"}

    db, _ = _make_db(
        is_support=AsyncMock(return_value=True),
        get_account_by_object_id=AsyncMock(return_value=account),
        get_gamer_by_id=AsyncMock(return_value=gamer),
    )
    bot = _make_bot()
    cb = _make_cb(f"release_deny:{account_oid}", user_id=99)

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.support_release_decision(cb, )

    db.set_account_status.assert_called_once()
    status_arg = db.set_account_status.call_args[0][1]
    assert status_arg == "active"

    gamer_calls = [c for c in bot.send_message.call_args_list if c[0][0] == 55555]
    assert len(gamer_calls) == 1
    assert "остаётся" in gamer_calls[0][0][1]


# ---------------------------------------------------------------------------
# Account screen (tests 17–18)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_account_screen_no_accounts_shows_fallback():
    """No accounts → message contains 'Залетай играть' balance fallback."""
    db, _ = _make_db(
        get_gamer_accounts=AsyncMock(return_value=[]),
    )
    bot = _make_bot()
    msg = _make_msg()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_account(msg, MagicMock())

    text = msg.answer.call_args[0][0]
    assert "Залетай играть" in text


@pytest.mark.asyncio
async def test_account_screen_shows_active_emoji():
    """One active account → message contains ✅ emoji from status_emoji map."""
    from tests.conftest import make_fake_gamer, make_fake_account

    gamer_doc = make_fake_gamer()
    account = make_fake_account(status="active", gamer_oid=gamer_doc["_id"])

    db, _ = _make_db(
        gamer=gamer_doc,
        get_gamer_accounts=AsyncMock(return_value=[account]),
        get_gamer_season_points=AsyncMock(return_value=500),
    )
    bot = _make_bot()
    msg = _make_msg()

    with patch.object(main, "db", db), patch.object(main, "bot", bot), patch.object(
        main, "TelegramState", _ts()
    ):
        await main.gamer_account(msg, MagicMock())

    text = msg.answer.call_args[0][0]
    assert "✅" in text
