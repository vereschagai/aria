from aiogram import types

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from functools import reduce

import texts
import markups
import buttons
import utils
from state import TelegramState

from mongodb import MongoDb
from google_api import GoogleSheets
from sheet_synchonizer import GoogleSheetSynchonizer


class OperatorController:
    def __init__(self, dp: Dispatcher, bot: Bot, db: MongoDb, google_api: GoogleSheets, synchonizer: GoogleSheetSynchonizer):
        self.dp = dp
        self.bot = bot
        self.db = db
        self.google_api = google_api
        self.synchonizer = synchonizer

    def init_handlers(self):
        self.dp.register_message_handler(self.__main, Text(buttons.back), state=TelegramState.leaderboard)
        self.dp.register_message_handler(self.__leaderboard, Text(buttons.leaderboard), state=TelegramState.operator_start)
        self.dp.register_message_handler(self.__leaderboard, Text(buttons.leaderboard), state=TelegramState.superadmin_start)
        self.dp.register_message_handler(self.__leaderboard, Text(buttons.leaderboard), state=TelegramState.admin_start)
        self.dp.register_message_handler(self.__leaderboard, Text(buttons.leaderboard), state=TelegramState.start)


    async def main(self, user_id):
        if await self.db.is_superadmin(user_id):
            await TelegramState.superadmin_start.set()
            await utils.safe_wrap(lambda: self.bot.send_message(user_id, texts.superadmin_start, reply_markup=markups.superadmin_start))
        elif await self.db.is_admin(user_id):
            await TelegramState.admin_start.set()
            await utils.safe_wrap(lambda: self.bot.send_message(user_id, texts.admin_start, reply_markup=markups.admin_start))
        elif await self.db.is_operator(user_id):
            state = self.dp.current_state(chat=user_id, user=user_id)
            await state.set_state(TelegramState.operator_start)
            await utils.safe_wrap(lambda: self.bot.send_message(user_id, "Че нада?", reply_markup=markups.operator_start))
        else:
            await TelegramState.start.set()
            sent_message = await utils.safe_wrap(lambda: self.bot.send_message(user_id, texts.gamer_start, reply_markup=markups.start, parse_mode="MarkdownV2", disable_web_page_preview=True))
            await utils.clean_messages(self.bot, self.db, user_id)
            await utils.add_message_history(self.db, sent_message)

    async def __main(self, message: types.Message):
        await utils.add_message_history(self.db, message)
        await self.main(message.from_user.id)

    async def __leaderboard(self, message: types.Message, state: FSMContext):
        await utils.add_message_history(self.db, message)
        
        accounts = await self.db.get_accounts({ "points.points": { "$gt": 0 } })
        leaderboard = {}
        for account in accounts:
            if "gamer" not in account or not account["gamer"]:
                continue
            if account["gamer"] not in leaderboard:
                leaderboard[account["gamer"]] = 0

            leaderboard[account["gamer"]] += account["points"]["points"]
        
        data = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
        await self.__print_leaderboard(message.from_user.id, data)


    async def __print_leaderboard(self, user_id, leaderboard_data, is_new_year = False):
        has_leaderboard = True

        db_config = await self.db.get_config()
        await TelegramState.leaderboard.set()

        gamer = await self.db.get_gamer(user_id)
        try:
            text = f'👑 *Leaderboard* 👑\n\n'
            if gamer:
                gamer_index = next(i for i, data in enumerate(leaderboard_data) if data[0] == gamer["username"])
                start_index = max(gamer_index - db_config["leaderboard_gap"], 0)
                end_index = gamer_index + db_config["leaderboard_gap"] + 1

                visible_data = leaderboard_data[start_index:end_index]
            else:
                gamer_index = 0
                start_index = 0
                end_index = len(leaderboard_data)

                visible_data = leaderboard_data

            if start_index > 0:
                text += '\.\.\.\n'

            for i, data in enumerate(visible_data):
                text += f'{"*" if i + start_index == gamer_index else ""}{i + start_index + 1}\. {"||Перефарми меня||" if i + start_index < gamer_index else utils.escape(f"@{data[0]}")} {data[1]} {("👑" if not is_new_year else "🎅") if i == 0 and start_index == 0 else ""}{"*" if i + start_index == gamer_index else ""}\n'

            if end_index < len(leaderboard_data):
                text += '\.\.\.'
                
        except StopIteration:
            has_leaderboard = False

        sent_message = await utils.safe_wrap(lambda: self.bot.send_message(user_id, text if has_leaderboard else texts.gamer_no_leaderboard, reply_markup=markups.back, parse_mode="MarkdownV2"))
        
        await utils.clean_messages(self.bot, self.db, user_id)
        await utils.add_message_history(self.db, sent_message)

