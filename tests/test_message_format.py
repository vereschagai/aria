"""
Message format and length tests — 14 tests covering:
  escape() correctness, full-message MarkdownV2 validity, and Telegram size limits.
"""

import sys
import os
import pytest
from bson import ObjectId
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))  # so conftest is importable

import utils
import texts
from conftest import assert_valid_markdownv2, make_fake_account


# ---------------------------------------------------------------------------
# Unit tests on utils.escape()  (tests 1–5)
# ---------------------------------------------------------------------------


def test_escape_plus():
    """`+` must be escaped as `\\+`."""
    result = utils.escape("+100")
    assert "\\+" in result


def test_escape_minus():
    """`-` must be escaped as `\\-`."""
    result = utils.escape("-50")
    assert "\\-" in result


def test_escape_dot():
    """`.` must be escaped as `\\.`."""
    result = utils.escape("Account.1")
    assert "\\." in result


def test_escape_parentheses():
    """`(` and `)` must each be escaped."""
    result = utils.escape("(test)")
    assert "\\(" in result
    assert "\\)" in result


def test_escape_profile_with_mixed_chars():
    """All reserved chars in a mixed string must be escaped; validator must pass."""
    raw = "My-Account.1 (Pro)"
    escaped = utils.escape(raw)
    assert "\\-" in escaped
    assert "\\." in escaped
    assert "\\(" in escaped
    assert "\\)" in escaped
    assert_valid_markdownv2(escaped)


# ---------------------------------------------------------------------------
# Full-message MarkdownV2 validation  (tests 6–8)
# ---------------------------------------------------------------------------


def test_pickup_success_message_valid_markdownv2():
    """texts.gamer_pickup_success with special-char dynamic content passes the validator."""
    msg = texts.gamer_pickup_success.format(
        profile=utils.escape("Account.1-Pro"),
        login=utils.escape("user+name"),
        password=utils.escape("pa$$word"),
    )
    assert_valid_markdownv2(msg)


def test_pickup_ineligible_message_valid_markdownv2():
    """Ineligible message with a reason containing special chars passes the validator."""
    reason = "Аккаунт acc.1 — недостаточно прогресса (нужно 50+ баллов)"
    msg = texts.gamer_pickup_ineligible.format(reason=utils.escape(reason))
    assert_valid_markdownv2(msg)


def test_release_sent_message_valid_markdownv2():
    """texts.gamer_release_account_sent with a profile containing special chars is valid."""
    msg = texts.gamer_release_account_sent.format(
        profile=utils.escape("My.Account-1")
    )
    assert_valid_markdownv2(msg)


# ---------------------------------------------------------------------------
# Progress history line escaping  (tests 9–10)
# ---------------------------------------------------------------------------


def _build_history_line(tower_points: int, delta: int) -> str:
    """Mirror the escape logic from gamer_release_account_select."""
    synced_at = datetime(2024, 1, 1, 12, 30)
    date = utils.escape(synced_at.strftime("%d.%m %H:%M"))
    tower = utils.escape(str(tower_points))
    sign = utils.escape("+") if delta >= 0 else ""
    delta_str = utils.escape(str(delta))
    return f"{date} → {tower} \\({sign}{delta_str}\\)"


def test_progress_history_line_positive_delta_valid_markdownv2():
    """History line with +500 delta produces a valid MarkdownV2 string."""
    line = _build_history_line(tower_points=1500, delta=500)
    assert_valid_markdownv2(line)
    assert "\\+" in line


def test_progress_history_line_negative_delta_valid_markdownv2():
    """History line with -100 delta produces a valid MarkdownV2 string."""
    line = _build_history_line(tower_points=900, delta=-100)
    assert_valid_markdownv2(line)
    assert "\\-" in line


# ---------------------------------------------------------------------------
# Message length limits  (tests 11–14)
# ---------------------------------------------------------------------------


def test_pickup_success_under_4096():
    """Pickup success message with 50-char profile/login/password is under Telegram limit."""
    msg = texts.gamer_pickup_success.format(
        profile=utils.escape("A" * 50),
        login=utils.escape("B" * 50),
        password=utils.escape("C" * 50),
    )
    assert len(msg) < 4096


def test_account_screen_10_accounts_under_4096():
    """Account screen with 10 accounts (default max) renders under Telegram's 4096-char limit."""
    accounts = [
        make_fake_account(profile=f"Acc{i}", status="active")
        for i in range(10)
    ]

    # Replicate the accounts_table building logic from gamer_account handler
    accounts_table = ""
    for account in accounts:
        history = account.get("progress_history", [])
        last_delta = history[-1]["delta"] if history else 0
        status_emoji = {
            "active": "✅",
            "escalated": "🚨",
            "released": "🔓",
            "inactive": "⛔",
            "pending_release": "⏳",
        }.get(account.get("status", "active"), "✅")
        accounts_table += (
            f"\n{utils.escape('---------------------------')}\n"
            f"\n{status_emoji} *{utils.escape(account['profile'])}*\n"
            f"Tower Points: {account['tower']['points']} "
            f"\\(\\+{last_delta} за последний синк\\)\n"
            f"Tower Rank: {account['tower']['rank']} \\| Floor: {account['tower']['floor']}\n"
            f"\nAccount:\n"
            f"    Login: `{utils.escape(account['login'])}`\n"
            f"    Password: `{utils.escape(account['password'])}`\n"
            f"\nProxy:\n"
            f"    Host: `{utils.escape(account['proxy'].get('host', ''))}`\n"
            f"    Port: `{account['proxy'].get('port', '')}`\n"
            f"    Login: `{utils.escape(account['proxy'].get('login', ''))}`\n"
            f"    Password: `{utils.escape(account['proxy'].get('password', ''))}`\n"
        )

    full_message = texts.gamer_account.format(
        address="0xTestAddress",
        referral=utils.escape("Нет"),
        referral_count=0,
        balance=1000,
        accounts_table=accounts_table,
        support_handle=utils.escape("@testsupp"),
    )

    assert len(full_message) < 4096


def test_release_notification_under_4096():
    """Support release notification with 100 history entries (last 5 shown) is under limit."""
    # Build 5 history lines (only last 5 are included)
    lines = []
    for i in range(5):
        synced_at = datetime(2024, 1, i + 1, 12, 0)
        date = utils.escape(synced_at.strftime("%d.%m %H:%M"))
        tower = utils.escape(str(1000 + i * 100))
        sign = utils.escape("+")
        delta = utils.escape(str(100 + i))
        lines.append(f"{date} → {tower} \\({sign}{delta}\\)")

    history_lines = "\n".join(lines)
    msg = texts.support_release_request.format(
        profile=utils.escape("TestProfile"),
        username=utils.escape("testgamer"),
        history=history_lines,
    )
    assert len(msg) < 4096


def test_callback_data_under_64_chars():
    """release_select callback data (prefix + ObjectId hex) fits in Telegram's 64-byte limit."""
    oid = ObjectId()
    data = f"release_select:{oid}"
    assert len(data) < 64
