"""
ProgressMonitor — inactivity detection and support escalation.

Called automatically after every sheet sync via GoogleSheetSynchonizer.

Inactivity is measured in calendar days (local time):
  - 1 calendar day without progress  → warn gamer (once per day)
  - N calendar days (inactivity_escalation_days config, default 3) → escalate to support
"""

from datetime import datetime, date

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import buttons
import texts
import utils
from mongodb import MongoDb


class ProgressMonitor:
    def __init__(self, bot: Bot, db: MongoDb):
        self.bot = bot
        self.db = db

    async def check_all(self):
        config = await self.db.get_config()
        escalation_days = config.get("inactivity_escalation_days", 3) if config else 3

        accounts = await self.db.get_active_assigned_accounts()
        today = date.today()
        today_ordinal = today.toordinal()

        for account in accounts:
            last_progress = account.get("last_progress_at")

            if last_progress is None:
                # No progress ever recorded — use most recent assignment date as baseline
                history = account.get("ownership_history", [])
                if history:
                    baseline = history[-1].get("assigned_at")
                else:
                    continue  # nothing to base inactivity on
            else:
                baseline = last_progress

            if baseline is None:
                continue

            # Ensure timezone-naive before .date() call
            if baseline.tzinfo is not None:
                baseline = baseline.replace(tzinfo=None)

            # Calendar-day diff: June 1 → June 3 = 2 days regardless of time-of-day
            days_inactive = (today - baseline.date()).days

            if days_inactive < 1:
                continue  # making progress, nothing to do

            # Deduplicate: only one action per calendar day per account
            last_notified_day = account.get("last_notified_day")
            if last_notified_day == today_ordinal:
                continue

            if days_inactive >= escalation_days and account.get("status") != "escalated":
                await self._escalate(account)
            elif days_inactive >= 1 and account.get("status") != "escalated":
                await self._warn_gamer(account, days_inactive)
                await self.db.set_account_status(
                    account["profile"],
                    account.get("status", "active"),
                    extra_fields={"last_notified_day": today_ordinal}
                )

    async def _warn_gamer(self, account: dict, days_inactive: int):
        """Send inactivity warning to the gamer who owns this account."""
        gamer_id = account.get("gamer_id")
        if not gamer_id:
            return

        gamer = await self.db.get_gamer_by_id(gamer_id)
        if not gamer or "id" not in gamer:
            return

        profile = account["profile"]
        text = texts.gamer_inactivity_warning.format(
            profile=utils.escape(profile),
            days=days_inactive
        )
        await utils.safe_wrap(lambda: self.bot.send_message(
            gamer["id"], text, parse_mode="MarkdownV2"
        ))

    async def _escalate(self, account: dict):
        """Escalate account to all support users and notify gamer."""
        profile = account["profile"]
        gamer_id = account.get("gamer_id")

        gamer = await self.db.get_gamer_by_id(gamer_id) if gamer_id else None
        gamer_tg_id = gamer["id"] if gamer else None
        gamer_username = gamer.get("username", "???") if gamer else "???"

        now = datetime.utcnow()

        # Mark account as escalated
        await self.db.set_account_status(
            profile,
            "escalated",
            extra_fields={
                "escalated_at": now,
                "last_notified_day": now.toordinal()
            }
        )

        # Build escalation summary — only this gamer's own entries
        gamer_history = [e for e in account.get("progress_history", []) if e.get("gamer_id") == gamer_id]
        last_entries = gamer_history[-5:] if len(gamer_history) >= 5 else gamer_history
        _hist_lines = []
        for e in last_entries:
            date  = utils.escape(e['synced_at'].strftime('%d.%m %H:%M'))
            tower = utils.escape(str(e['tower_points']))
            sign  = utils.escape('+') if e['delta'] >= 0 else ''
            delta = utils.escape(str(e['delta']))
            _hist_lines.append(f"{date} → {tower} \\({sign}{delta}\\)")
        history_lines = "\n".join(_hist_lines) or "_нет данных_"

        escalation_text = texts.support_escalation.format(
            profile=utils.escape(profile),
            username=utils.escape(f"@{gamer_username}"),
            history=history_lines
        )

        support_users = await self.db.get_support_users()

        # Use account _id (24-char hex) in callback_data to stay within Telegram's 64-byte limit
        account_oid = str(account["_id"])
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton(buttons.release_pool,   callback_data=f"release_pool:{account_oid}"),
            InlineKeyboardButton(buttons.release_finish, callback_data=f"release_finish:{account_oid}"),
        )
        # No deny button for inactivity escalations

        pending_proof = account.get("pending_proof")

        for support_user in support_users:
            try:
                await utils.safe_wrap(lambda su=support_user: self.bot.send_message(
                    su["id"],
                    escalation_text,
                    reply_markup=markup,
                    parse_mode="MarkdownV2"
                ))
                # Forward gamer proof if any
                if pending_proof:
                    await utils.safe_wrap(lambda su=support_user: self.bot.forward_message(
                        su["id"],
                        pending_proof["chat_id"],
                        pending_proof["message_id"]
                    ))
            except Exception as e:
                print(f"[ProgressMonitor] Failed to notify support user {support_user['id']}: {e}")

        # Notify gamer of escalation
        if gamer_tg_id:
            await utils.safe_wrap(lambda: self.bot.send_message(
                gamer_tg_id,
                texts.gamer_escalated.format(profile=utils.escape(profile)),
                parse_mode="MarkdownV2"
            ))
