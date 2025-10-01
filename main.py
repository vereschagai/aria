import os
import asyncio
import aiocron
from datetime import datetime, timedelta
from credit_card_checker import CreditCardChecker
from bson.objectid import ObjectId
from threading import Timer
import base64
import uuid
from tenacity import retry, wait_exponential

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import CommandStart, Text
from aiogram.contrib.fsm_storage.mongo import MongoStorage
from aiogram.utils import executor

from cryptoaddress import EthereumAddress

import texts
import buttons

import markups
from mongodb import MongoDb
from state import TelegramState
from google_api import GoogleSheets
from sheet_synchonizer import GoogleSheetSynchonizer
from operator_controller import OperatorController
from config import config
import utils

# TEST_BOT_TOKEN = '5070144577:AAE5gEcC6nC7ZwJ4lPfS5yg-ukMprsPZqbw'
TEST_BOT_TOKEN = "5573313924:AAFKSsjngw_m5PsIe3bU4wKsZsb8kgtDbnM" # LOCAL TEST

# Telegram
BOT_TOKEN = os.environ.get('BOT_TOKEN', TEST_BOT_TOKEN)
superadmins = [
    {
        'id': 208809955,
        'name': 'ivanvereschaga',
        'stat_marker': 'VIP'
    }
]

# MongoDB
DB_HOST = os.environ.get('DB_HOST', "localhost")
DB_PORT = int(os.environ.get('DB_PORT', 27017))
DB_NAME = os.environ.get('DB_NAME', "aria")
DB_USERNAME = os.environ.get('DB_USERNAME')
DB_PASSWORD = os.environ.get('DB_PASSWORD')

# Google Sheets
ARIA_GAMEPLAY_SHEET_ID = '18NtTSuIWVU9sGdnJ_NGlnsowPD1oBtUyZmCULvmAcZ4'

bot = Bot(token=BOT_TOKEN)
Bot.set_current(bot)

storage = MongoStorage(host=DB_HOST, port=DB_PORT, db_name=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD)
dp = Dispatcher(bot=bot, storage=storage, loop=asyncio.get_event_loop())

db = MongoDb(host=DB_HOST, port=DB_PORT, db_name=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD)
api = GoogleSheets(
    aria_gameplay_sheet_id=ARIA_GAMEPLAY_SHEET_ID
)

synchonizer = GoogleSheetSynchonizer(db, api)

operator_controller = OperatorController(dp, bot, db, api, synchonizer)


async def init():
    for superadmin in superadmins:
        if not await db.is_superadmin(superadmin['id']):
            await db.add_superadmin({ "id": superadmin['id'], "username": superadmin['name'] })

    db_config = await db.get_config()
    for field in config:
        if not db_config or field not in db_config:
            await db.update_config(field, config[field])

    # db_config = await db.get_config()

    # if await db.count_gamers({}) == 0:
    #     gamers = api.get_existent_gamers()
    #     for gamer in gamers:
    #         if "id" in gamer and not await db.is_gamer({ "id": gamer["id"] }) or "username" in gamer and not await db.is_gamer({ "username": gamer["username"] }):
    #             await db.add_gamer(gamer["id"], gamer["username"], gamer["referral"], gamer["address"])


asyncio.run_coroutine_threadsafe(init(), dp.loop)


@dp.message_handler(CommandStart(), state=None)
@dp.message_handler(CommandStart(), state=TelegramState.start)
@dp.message_handler(CommandStart(), state=TelegramState.referral)
@dp.message_handler(CommandStart(), state=TelegramState.account)
@dp.message_handler(CommandStart(), state=TelegramState.address)
@dp.message_handler(CommandStart(), state=TelegramState.leaderboard)
@dp.message_handler(CommandStart(), state=TelegramState.superadmin_start)
@dp.message_handler(CommandStart(), state=TelegramState.operator_start)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.superadmin_add_admin)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.superadmin_feed)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.admin_add_validator)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.admin_add_payer)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.admin_add_operator)
@dp.message_handler(Text(equals=buttons.cancel), state=TelegramState.superadmin_remove_admin_confirm)
@dp.message_handler(Text(equals=buttons.cancel), state=TelegramState.admin_remove_validator_confirm)
@dp.message_handler(Text(equals=buttons.cancel), state=TelegramState.admin_remove_operator_confirm)
@dp.message_handler(Text(equals=buttons.cancel), state=TelegramState.admin_remove_payer_confirm)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.account)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.referral)
async def start(message: types.Message, state: FSMContext):
    if await db.is_superadmin(message.from_user.id):
        print("is_superadmin")
        await TelegramState.superadmin_start.set()

        await utils.safe_wrap(lambda: message.answer(texts.superadmin_start, reply_markup=markups.superadmin_start))
    elif await db.is_admin(message.from_user.id):
        print("is_admin")
        await TelegramState.admin_start.set()

        if await db.get_admin({ "username": message.from_user.username }) == None:
            await db.db["admin"].update_one({ "id": message.from_user.id }, { "$set": { "username": message.from_user.username } })

        await utils.safe_wrap(lambda: message.answer(texts.admin_start, reply_markup=markups.admin_start))
    elif await db.is_operator(message.from_user.id):
        print("is_operator")
        await operator_controller.main(message.from_user.id)
    else:
        data = await state.get_data()
        
        has_username = bool(message.from_user.username)
        newcomer = None

        if await db.is_gamer({ "id": message.from_user.id }):
            available = True
            if message.from_user.username and not await db.is_gamer({ "username": message.from_user.username }):
                await db.update_gamer({ "id": message.from_user.id }, { "username": message.from_user.username})
        elif has_username and await db.is_gamer({ "username": message.from_user.username }):
            available = True
            await db.update_gamer({ "username": message.from_user.username }, { "id": message.from_user.id })
        else:
            newcomer = True
            referral = None

            parts = message.text.split(' ')
            if len(parts) == 2 and parts[1].isdigit():
                referral = int(parts[1])

            if referral == message.from_user.id or (not await db.is_gamer({ "id": referral }) and not await db.is_superadmin(referral) and not await db.is_admin(referral) and not await db.is_operator(referral)):
                referral = None

            if not has_username and referral:
                await state.set_data({ "referral": referral })
            elif has_username:
                if "referral" in data:
                    referral = data["referral"]

            available = referral != None
        
        if not available:
            sent_message = await utils.safe_wrap(lambda: message.answer(texts.gamer_only_invite_access, parse_mode="MarkdownV2"))
        elif not has_username:
            sent_message = await utils.safe_wrap(lambda: message.answer(texts.gamer_no_username, parse_mode="MarkdownV2"))
        else:
            if newcomer:
                await state.update_data({ "id": message.from_user.id, "username": message.from_user.username, "referral": referral })

                await db.add_gamer(message.from_user.id, message.from_user.username, referral)
                
            await TelegramState.start.set()
            sent_message = await utils.safe_wrap(lambda: message.answer(texts.gamer_start, reply_markup=markups.start, parse_mode="MarkdownV2", disable_web_page_preview=True))

        await utils.add_message_history(db, message)
        await utils.clean_messages(bot, db, message.from_user.id)
        await utils.clean_messages(bot, db, message.from_user.id, "game")

        await utils.add_message_history(db, sent_message)


@dp.message_handler(Text(equals=buttons.admin_grab_accounts), state=TelegramState.superadmin_start)
async def superadmin_grab_accounts(message: types.Message):
    await synchonizer.grab_accounts()

    await utils.safe_wrap(lambda: message.answer(texts.admin_grab_account_done, reply_markup=markups.superadmin_start))


@dp.message_handler(Text(equals=buttons.configuration), state=TelegramState.superadmin_start)
async def superadmin_configuration(message: types.Message):
    db_config = await db.get_config()

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(buttons.back, callback_data="back"))
    for field in db_config:
        if field == "_id":
            continue

        markup.add(types.InlineKeyboardButton(field + ": " + str(db_config[field]), callback_data=field))

    await TelegramState.superadmin_configuration.set()
    await utils.safe_wrap(lambda: message.answer(texts.superadmin_configuration, reply_markup=markup))

@dp.callback_query_handler(state=TelegramState.superadmin_configuration)
async def superadmin_edit_configuration(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == "back":
        await TelegramState.superadmin_start.set()
        await callback_query.answer("")
        await utils.safe_wrap(lambda: bot.send_message(callback_query.from_user.id, texts.superadmin_start, reply_markup=markups.superadmin_start))

        return

    db_config = await db.get_config()
    if callback_query.data in db_config:
        await TelegramState.superadmin_edit_configuration.set()

        field = callback_query.data
        value = db_config[field]

        await state.set_data({ "field": field })

        await callback_query.answer("")
        await utils.safe_wrap(lambda: bot.send_message(callback_query.from_user.id, texts.superadmin_edit_configuration.format(field=field, value=value), reply_markup=types.ReplyKeyboardRemove()))
    else:
        await callback_query.answer("")
        await TelegramState.superadmin_start.set()
        await utils.safe_wrap(lambda: bot.send_message(callback_query.from_user.id, texts.internal_error, reply_markup=markups.superadmin_start))

@dp.message_handler(state=TelegramState.superadmin_edit_configuration)
async def superadmin_edit_value_configuration(message: types.Message, state: FSMContext):
    data = await state.get_data()

    field = data["field"]

    if message.text.lower() in ["true", "false"] if field == "validation_live" else message.text.isdigit():
        value = message.text.lower() == "true" if field == "validation_live" else int(message.text)
        await db.update_config(field, value)

        await state.reset_data()

        await TelegramState.superadmin_start.set()
        await utils.safe_wrap(lambda: message.answer(texts.superadmin_config_updated.format(field=field, value=value), reply_markup=markups.superadmin_start))
    else:
        await utils.safe_wrap(lambda: message.answer(texts.superadmin_config_value_wrong.format(field=field)))

@dp.message_handler(Text(equals=buttons.feed), state=TelegramState.superadmin_start)
async def superadmin_feed(message: types.Message):
    await TelegramState.superadmin_feed.set()
    await utils.safe_wrap(lambda: message.answer(texts.superadmin_feed, reply_markup=markups.back))

@dp.message_handler(content_types=types.ContentType.ANY, state=TelegramState.superadmin_feed)
async def superadmin_feed_send(message: types.Message):
    gamers = await db.get_gamers({})
    for gamer in gamers:
        try:
            if "id" in gamer:
                await message.copy_to(gamer["id"])
        except Exception:
            continue

    await TelegramState.superadmin_start.set()
    await utils.safe_wrap(lambda: message.answer(texts.superadmin_feed_sent, reply_markup=markups.superadmin_start))

@dp.message_handler(Text(equals=buttons.superadmin_add_admin), state=TelegramState.superadmin_start)
# @dp.message_handler(Text(equals=buttons.admin_add_validator), state=TelegramState.superadmin_start)
# @dp.message_handler(Text(equals=buttons.admin_add_validator), state=TelegramState.admin_start)
@dp.message_handler(Text(equals=buttons.admin_add_payer), state=TelegramState.superadmin_start)
@dp.message_handler(Text(equals=buttons.admin_add_payer), state=TelegramState.admin_start)
@dp.message_handler(Text(equals=buttons.admin_add_operator), state=TelegramState.superadmin_start)
@dp.message_handler(Text(equals=buttons.admin_add_operator), state=TelegramState.admin_start)
async def admin_add(message: types.Message):
    if message.text == buttons.superadmin_add_admin:
        await TelegramState.superadmin_add_admin.set()

        await utils.safe_wrap(lambda: message.answer(texts.superadmin_add, reply_markup=markups.back))
    # elif message.text == buttons.admin_add_validator:
    #     await TelegramState.admin_add_validator.set()

    #     await utils.safe_wrap(lambda: message.answer(texts.admin_add.format(contragent="валидатор"), reply_markup=markups.back)
    elif message.text == buttons.admin_add_payer:
        await TelegramState.admin_add_payer.set()

        await utils.safe_wrap(lambda: message.answer(texts.admin_add.format(contragent="кассир"), reply_markup=markups.back))
    elif message.text == buttons.admin_add_operator:
        await TelegramState.admin_add_operator.set()

        await utils.safe_wrap(lambda: message.answer(texts.admin_add.format(contragent="оператор"), reply_markup=markups.back))

@dp.message_handler(content_types=types.ContentType.CONTACT, state=TelegramState.superadmin_add_admin)
@dp.message_handler(content_types=types.ContentType.CONTACT, state=TelegramState.admin_add_validator)
@dp.message_handler(content_types=types.ContentType.CONTACT, state=TelegramState.admin_add_payer)
@dp.message_handler(content_types=types.ContentType.CONTACT, state=TelegramState.admin_add_operator)
async def admin_added(message : types.Message, state: FSMContext):
    if not message.contact.user_id:
        await utils.safe_wrap(lambda: message.answer(texts.admin_add_wrong))
        return

    if await state.get_state() == "TelegramState:superadmin_add_admin":
        await TelegramState.superadmin_start.set()

        if not await db.is_admin(message.contact.user_id):
            await db.add_admin(message.contact)

            await utils.safe_wrap(lambda: message.answer(texts.superadmin_added.format(name=message.contact.full_name), reply_markup=markups.superadmin_start))
        else:
            await utils.safe_wrap(lambda: message.answer(texts.superadmin_add_exists.format(name=message.contact.full_name), reply_markup=markups.superadmin_start))
    else:
        isValidator = await state.get_state() == "TelegramState:admin_add_validator"
        isOperator = await state.get_state() == "TelegramState:admin_add_operator"
        contragent = "Валидатор" if isValidator else "Оператор" if isOperator else "Кассир"

        isSuperadmin = await db.is_superadmin(message.from_user.id)

        if isSuperadmin:
            await TelegramState.superadmin_start.set()
        else:
            await TelegramState.admin_start.set()

        markup = markups.superadmin_start if isSuperadmin else markups.admin_start

        exists = await db.is_validator(message.contact.user_id) if isValidator else await db.is_operator(message.contact.user_id) if isOperator else await db.is_payer(message.contact.user_id)
        if not exists:
            if isValidator:
                await db.add_validator(message.contact)
            elif isOperator:
                await db.add_operator(message.contact)
            else:
                await db.add_payer(message.contact)

            await utils.safe_wrap(lambda: message.answer(texts.admin_added.format(contragent=contragent, name=message.contact.full_name), reply_markup=markup))
        else:
            await utils.safe_wrap(lambda: message.answer(texts.admin_add_exists.format(contragent=contragent, name=message.contact.full_name), reply_markup=markup))

@dp.message_handler(content_types=types.ContentType.ANY, state=TelegramState.superadmin_add_admin)
@dp.message_handler(content_types=types.ContentType.ANY, state=TelegramState.admin_add_validator)
@dp.message_handler(content_types=types.ContentType.ANY, state=TelegramState.admin_add_operator)
@dp.message_handler(content_types=types.ContentType.ANY, state=TelegramState.admin_add_payer)
async def admin_added_error(message: types.Message, state: FSMContext):
    if await state.get_state() == "TelegramState:superadmin_add_admin":
        await utils.safe_wrap(lambda: message.answer(texts.superadmin_added_error))
    else:
        isValidator = await state.get_state() == "TelegramState:admin_add_validator"
        isOperator = await state.get_state() == "TelegramState:admin_add_operator"

        contragent = "валидатор" if isValidator else "оператор" if isOperator else "кассир"
        await utils.safe_wrap(lambda: message.answer(texts.admin_added_error.format(contragent=contragent)))


@dp.message_handler(Text(equals=buttons.superadmin_remove_admin), state=TelegramState.superadmin_start)
# @dp.message_handler(Text(equals=buttons.admin_remove_validator), state=TelegramState.admin_start)
# @dp.message_handler(Text(equals=buttons.admin_remove_validator), state=TelegramState.superadmin_start)
@dp.message_handler(Text(equals=buttons.admin_remove_payer), state=TelegramState.admin_start)
@dp.message_handler(Text(equals=buttons.admin_remove_payer), state=TelegramState.superadmin_start)
@dp.message_handler(Text(equals=buttons.admin_remove_operator), state=TelegramState.admin_start)
@dp.message_handler(Text(equals=buttons.admin_remove_operator), state=TelegramState.superadmin_start)
async def admin_remove(message: types.Message):
    isSuperadmin = message.text == buttons.superadmin_remove_admin
    # isValidator = message.text == buttons.admin_remove_validator
    isOperator = message.text == buttons.admin_remove_operator

    count = await db.count_admins({}) if isSuperadmin else await db.count_operators({}) if isOperator else await db.count_payers({})
    if count > 0:
        markup = types.InlineKeyboardMarkup(row_width=1)
        entities = await db.get_admins() if isSuperadmin else await db.get_operators() if isOperator else await db.get_payers({})

        for entity in entities:
            label = (entity["username"] + " " if "username" in entity else "") + entity["phone"]
            markup.add(types.InlineKeyboardButton(label, callback_data=str(entity["id"])))

        markup.add(types.InlineKeyboardButton(buttons.back, callback_data="back"))

        if isSuperadmin:
            await TelegramState.superadmin_remove_admin.set()
        elif isOperator:
            await TelegramState.admin_remove_operator.set()
        else:
            await TelegramState.admin_remove_payer.set()

        await utils.safe_wrap(lambda: message.answer(texts.admin_remove, reply_markup=markup))
    else:
        contragent = "оператор" if isOperator else "кассир"
        text = texts.superadmin_remove_empty if isSuperadmin else texts.admin_remove_empty.format(contragent=contragent)
        markup = markups.superadmin_start if await db.is_superadmin(message.from_user.id) else markups.admin_start

        await utils.safe_wrap(lambda: message.answer(text, reply_markup=markup))

@dp.callback_query_handler(state=TelegramState.superadmin_remove_admin)
@dp.callback_query_handler(state=TelegramState.admin_remove_validator)
@dp.callback_query_handler(state=TelegramState.admin_remove_operator)
@dp.callback_query_handler(state=TelegramState.admin_remove_payer)
async def admin_remove_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    isSuperadmin = await state.get_state() == "TelegramState:superadmin_remove_admin"

    if callback_query.data == "back":
        isSuperadmin = await db.is_superadmin(callback_query.from_user.id)

        if isSuperadmin:
            await TelegramState.superadmin_start.set()
        else:
            await TelegramState.admin_start.set()

        await callback_query.answer("")
        await utils.safe_wrap(lambda: bot.send_message(callback_query.from_user.id, texts.superadmin_start if isSuperadmin else texts.admin_start, reply_markup=markups.superadmin_start if isSuperadmin else markups.admin_start))

        return

    isValidator = await state.get_state() == "TelegramState:admin_remove_validator"
    isOperator = await state.get_state() == "TelegramState:admin_remove_operator"

    search = { "id": int(callback_query.data) }
    entity = await db.get_admin(search) if isSuperadmin else await db.get_validator(search) if isValidator else await db.get_operator(search) if isOperator else await db.get_payer(search)

    if entity != None:
        if isSuperadmin:
            await TelegramState.superadmin_remove_admin_confirm.set()
        elif isValidator:
            await TelegramState.admin_remove_validator_confirm.set()
        elif isOperator:
            await TelegramState.admin_remove_operator_confirm.set()
        else:
            await TelegramState.admin_remove_payer_confirm.set()

        await state.set_data(search)

        await callback_query.answer("")

        name = entity["username"] if "username" in entity else entity["phone"]

        contragent = "валидатор" if isValidator else "оператор" if isOperator else "кассир"
        await utils.safe_wrap(lambda: bot.send_message(callback_query.from_user.id, texts.superadmin_remove_confirm.format(username=name) if isSuperadmin else texts.admin_remove_confirm.format(contragent=contragent, username=name), reply_markup=markups.confirm))
    else:
        await utils.safe_wrap(lambda: bot.send_message(callback_query.from_user.id, texts.admin_remove_confirm_error))

@dp.message_handler(Text(equals=buttons.confirm), state=TelegramState.superadmin_remove_admin_confirm)
@dp.message_handler(Text(equals=buttons.confirm), state=TelegramState.admin_remove_validator_confirm)
@dp.message_handler(Text(equals=buttons.confirm), state=TelegramState.admin_remove_operator_confirm)
@dp.message_handler(Text(equals=buttons.confirm), state=TelegramState.admin_remove_payer_confirm)
async def admin_remove_confirmed(message: types.Message, state: FSMContext):
    isSuperadmin = await db.is_superadmin(message.from_user.id)

    isAdmin = await state.get_state() == "TelegramState:superadmin_remove_admin_confirm"
    isValidator = await state.get_state() == "TelegramState:admin_remove_validator_confirm"
    isOperator = await state.get_state() == "TelegramState:admin_remove_operator_confirm"

    search = await state.get_data()
    entity = await db.get_admin(search) if isAdmin else await db.get_validator(search) if isValidator else await db.get_operator(search) if isOperator else await db.get_payer(search)

    if isSuperadmin:
        await TelegramState.superadmin_start.set()
    else:
        await TelegramState.admin_start.set()

    if isAdmin:
        await db.remove_admin(search)
    elif isValidator:
        await db.remove_validator(search)
    elif isOperator:
        await db.remove_operator(search)
    else:
        await db.remove_payer(search)

    contragent_state = dp.current_state(chat=entity["id"], user=entity["id"])
    await contragent_state.finish()

    name = entity["username"] if "username" in entity else entity["phone"]
    contragent = "Валидатор" if isValidator else "Оператор" if isOperator else "Кассир"
    text = texts.superadmin_removed.format(username=name) if isAdmin else texts.admin_removed.format(contragent=contragent, username=name)
    markup = markups.superadmin_start if isSuperadmin else markups.admin_start
    await utils.safe_wrap(lambda: message.answer(text, reply_markup=markup))


@dp.message_handler(Text(equals=buttons.referral), state=TelegramState.start)
# @dp.message_handler(Text(equals=buttons.referral), state=TelegramState.admin_start)
# @dp.message_handler(Text(equals=buttons.referral), state=TelegramState.superadmin_start)
async def gamer_referral_link(message: types.Message, state: FSMContext):
    me = await bot.get_me()
    referral_link = f'https://t.me/{me.username}?start={message.from_user.id}'

    await TelegramState.referral.set()
    sent_message = await utils.safe_wrap(lambda: message.answer(texts.gamer_referral_link.format(link=utils.escape(referral_link)), reply_markup=markups.back, parse_mode="MarkdownV2", disable_web_page_preview=True))

    await utils.add_message_history(db, message)
    await utils.clean_messages(bot, db, message.from_user.id)

    await utils.add_message_history(db, sent_message)

@dp.message_handler(Text(equals=buttons.account), state=TelegramState.start)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.address)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.change_address)
async def gamer_account(message: types.Message, state: FSMContext):
    gamer = await db.get_gamer(message.from_user.id)
    if "referral" in gamer and gamer["referral"]:
        referral_gamer = await db.get_gamer(gamer["referral"])
        referral = ("@" + referral_gamer["username"]) if referral_gamer != None else "Админ"
    else:
        referral = "Нет"

    referral_count = await db.count_gamers({ "referral": message.from_user.id })
    
    balance = 'Залетай играть 😉'
    accounts_table = ''

    has_address = "address" in gamer and gamer["address"] != None
    address = gamer["address"] if has_address else "*добавь адрес кошелька для выплат*"
    markup = markups.backaddresschange if has_address else markups.backaddressadd

    accounts = await db.get_accounts({ "gamer": message.from_user.username }, sort = [( 'points.points', -1 )])
    if len(accounts) > 0:
        balance = 0

        for account in accounts:
            balance += account["points"]
            accounts_table += f'''\n{utils.escape('---------------------------')}\n
Points: {account["points"]["points"]}
Rank: {account["points"]["rank"]}

Tower Points: {account["tower"]["points"]}
Tower Rank: {account["tower"]["rank"]}
Tower Floor: {account["tower"]["floor"]}

Account:
    Login: `{utils.escape(account["login"])}`
    Password: `{utils.escape(account["password"])}`

Proxy:
    Host: `{utils.escape(account["proxy"]["host"])}`
    Port: `{account["proxy"]["port"]}`
    Login: `{utils.escape(account["proxy"]["login"])}`
    Password: `{utils.escape(account["proxy"]["password"])}`\n'''

    await TelegramState.account.set()
    sent_message = await utils.safe_wrap(lambda: message.answer(texts.gamer_account.format(address=address, referral=utils.escape(referral), referral_count=referral_count, balance=balance, accounts_table=accounts_table), reply_markup=markup, parse_mode="MarkdownV2"))
    
    await utils.add_message_history(db, message)
    await utils.clean_messages(bot, db, message.from_user.id)
    await utils.add_message_history(db, sent_message)

@dp.message_handler(Text(equals=buttons.add_address), state=TelegramState.account)
async def gamer_add_address(message: types.Message, state: FSMContext):
    await TelegramState.address.set()
    sent_message = await utils.safe_wrap(lambda: message.answer(texts.gamer_address, reply_markup=markups.back, parse_mode="MarkdownV2"))

    await utils.add_message_history(db, message)
    await utils.clean_messages(bot, db, message.from_user.id)

    await utils.add_message_history(db, sent_message)

@dp.message_handler(Text(equals=buttons.change_address), state=TelegramState.account)
async def gamer_change_address(message: types.Message, state: FSMContext):
    await TelegramState.change_address.set()
    sent_message = await utils.safe_wrap(lambda: message.answer(texts.gamer_change_address, reply_markup=markups.back))

    await utils.add_message_history(db, message)
    await utils.clean_messages(bot, db, message.from_user.id)

    await utils.add_message_history(db, sent_message)

@dp.message_handler(state=TelegramState.address)
@dp.message_handler(state=TelegramState.change_address)
async def gamer_new_address(message: types.Message, state: FSMContext):
    await utils.add_message_history(db, message)

    try:
        EthereumAddress(message.text)

        await db.update_gamer_address(message.from_user.id, message.text)

        await gamer_account(message, state)
    except ValueError:
        sent_message = await utils.safe_wrap(lambda: message.answer(texts.gamer_address_wrong, reply_markup=markups.back, parse_mode="MarkdownV2"))
        
        await utils.add_message_history(db, sent_message)


operator_controller.init_handlers()
if __name__ == '__main__':
    print("Bot started")
    executor.start_polling(dp, skip_updates=False)