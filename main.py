import os
import asyncio
import traceback
from datetime import datetime

from bson import ObjectId

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
from progress_monitor import ProgressMonitor
from config import config
import utils

safe_wrap = utils.safe_wrap

# Telegram
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")
superadmins = [
    {
        'id': 208809955,
        'name': 'PoluBotOK',
    }
]

# MongoDB
DB_HOST = os.environ.get('DB_HOST', "localhost")
DB_PORT = int(os.environ.get('DB_PORT', 27017))
DB_NAME = os.environ.get('DB_NAME', "aria")
DB_USERNAME = os.environ.get('DB_USERNAME')
DB_PASSWORD = os.environ.get('DB_PASSWORD')

# Google Sheets
ARIA_SHEET_ID = os.environ.get('ARIA_SHEET_ID')
if not ARIA_SHEET_ID:
    raise RuntimeError("ARIA_SHEET_ID environment variable is required")

BOT_USERNAME = ""  # populated at startup via bot.get_me()

bot = Bot(token=BOT_TOKEN)
Bot.set_current(bot)

storage = MongoStorage(host=DB_HOST, port=DB_PORT, db_name=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD)
dp = Dispatcher(bot=bot, storage=storage, loop=asyncio.get_event_loop())

db = MongoDb(host=DB_HOST, port=DB_PORT, db_name=DB_NAME, username=DB_USERNAME, password=DB_PASSWORD)
api = GoogleSheets(
    aria_gameplay_sheet_id=ARIA_SHEET_ID
)

progress_monitor = ProgressMonitor(bot, db)
synchonizer = GoogleSheetSynchonizer(db, api, progress_monitor=progress_monitor)


async def init():
    global BOT_USERNAME
    bot_me = await bot.get_me()
    BOT_USERNAME = bot_me.username

    await db.ensure_indexes()

    for superadmin in superadmins:
        if not await db.is_superadmin(superadmin['id']):
            await db.add_superadmin({ "id": superadmin['id'], "username": superadmin['name'] })
        await db.ensure_invite_token(superadmin['id'], "superadmin")

    db_config = await db.get_config()
    for field in config:
        if not db_config or field not in db_config:
            await db.update_config(field, config[field])


asyncio.run_coroutine_threadsafe(init(), dp.loop)


# =============================================================================
# /start and universal back/cancel — role resolution entry point
# =============================================================================

@dp.message_handler(CommandStart(), state=None)
@dp.message_handler(CommandStart(), state=TelegramState.start)
@dp.message_handler(CommandStart(), state=TelegramState.referral)
@dp.message_handler(CommandStart(), state=TelegramState.account)
@dp.message_handler(CommandStart(), state=TelegramState.address)
@dp.message_handler(CommandStart(), state=TelegramState.leaderboard)
@dp.message_handler(CommandStart(), state=TelegramState.superadmin_start)
@dp.message_handler(CommandStart(), state=TelegramState.support_start)
@dp.message_handler(CommandStart(), state=TelegramState.gamer_release_account)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.superadmin_add_admin)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.superadmin_feed)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.admin_add_support)
@dp.message_handler(Text(equals=buttons.cancel), state=TelegramState.superadmin_remove_admin_confirm)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.account)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.referral)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.gamer_release_account)
async def start(message: types.Message, state: FSMContext):
    if await db.is_superadmin(message.from_user.id):
        print("is_superadmin")
        await TelegramState.superadmin_start.set()
        await utils.safe_wrap(lambda: message.answer(texts.superadmin_start, reply_markup=markups.superadmin_start))
    elif await db.is_support(message.from_user.id):
        print("is_support")
        await TelegramState.support_start.set()
        await utils.safe_wrap(lambda: message.answer(texts.support_start_text, reply_markup=markups.support_start, parse_mode="MarkdownV2"))
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
            if len(parts) == 2:
                token_doc = await db.get_invite_token_by_uuid(parts[1])
                if token_doc:
                    referral = token_doc["issuer_id"]

            if referral == message.from_user.id or (not await db.is_gamer({ "id": referral }) and not await db.is_superadmin(referral) and not await db.is_support(referral)):
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


# =============================================================================
# Superadmin — sheet sync, configuration, broadcast
# =============================================================================

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
                await utils.safe_wrap(lambda g=gamer: message.copy_to(g["id"]))
        except Exception:
            continue

    await TelegramState.superadmin_start.set()
    await utils.safe_wrap(lambda: message.answer(texts.superadmin_feed_sent, reply_markup=markups.superadmin_start))


@dp.message_handler(Text(equals=buttons.superadmin_invite_link, ignore_case=True),
                    state=TelegramState.superadmin_start)
async def superadmin_invite_link(message: types.Message):
    token = await db.ensure_invite_token(message.from_user.id, "superadmin")
    link = f"t.me/{BOT_USERNAME}?start={token['uuid']}"
    await utils.add_message_history(db, message)
    await utils.clean_messages(bot, db, message.from_user.id)
    sent = await safe_wrap(lambda: message.answer(texts.invite_link.format(link=link), disable_web_page_preview=True))
    await utils.add_message_history(db, sent)


# =============================================================================
# Superadmin — add/remove superadmins and support
# =============================================================================

@dp.message_handler(Text(equals=buttons.superadmin_add_admin), state=TelegramState.superadmin_start)
@dp.message_handler(Text(equals=buttons.admin_add_support), state=TelegramState.superadmin_start)
async def admin_add(message: types.Message):
    if message.text == buttons.superadmin_add_admin:
        await TelegramState.superadmin_add_admin.set()
        await utils.safe_wrap(lambda: message.answer(texts.superadmin_add, reply_markup=markups.back))
    elif message.text == buttons.admin_add_support:
        await TelegramState.admin_add_support.set()
        await utils.safe_wrap(lambda: message.answer(texts.admin_add_support_prompt, reply_markup=markups.back))

@dp.message_handler(content_types=types.ContentType.CONTACT, state=TelegramState.superadmin_add_admin)
@dp.message_handler(content_types=types.ContentType.CONTACT, state=TelegramState.admin_add_support)
async def admin_added(message: types.Message, state: FSMContext):
    if not message.contact.user_id:
        await utils.safe_wrap(lambda: message.answer(texts.admin_add_wrong))
        return

    current_state = await state.get_state()

    if current_state == "TelegramState:superadmin_add_admin":
        await TelegramState.superadmin_start.set()
        if not await db.is_superadmin(message.contact.user_id):
            await db.add_superadmin({"id": message.contact.user_id, "username": message.contact.full_name})
            await db.ensure_invite_token(message.contact.user_id, "superadmin")
            await utils.safe_wrap(lambda: message.answer(texts.superadmin_added.format(name=message.contact.full_name), reply_markup=markups.superadmin_start))
        else:
            await utils.safe_wrap(lambda: message.answer(texts.superadmin_add_exists.format(name=message.contact.full_name), reply_markup=markups.superadmin_start))

    else:  # admin_add_support
        await TelegramState.superadmin_start.set()
        if not await db.is_support(message.contact.user_id):
            await db.add_support(message.contact)
            await db.ensure_invite_token(message.contact.user_id, "support")
            await utils.safe_wrap(lambda: message.answer(texts.admin_added.format(contragent="Поддержка", name=message.contact.full_name), reply_markup=markups.superadmin_start))
        else:
            await utils.safe_wrap(lambda: message.answer(texts.admin_add_exists.format(contragent="Поддержка", name=message.contact.full_name), reply_markup=markups.superadmin_start))

@dp.message_handler(content_types=types.ContentType.ANY, state=TelegramState.superadmin_add_admin)
@dp.message_handler(content_types=types.ContentType.ANY, state=TelegramState.admin_add_support)
async def admin_added_error(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == "TelegramState:superadmin_add_admin":
        await utils.safe_wrap(lambda: message.answer(texts.superadmin_added_error))
    else:  # admin_add_support
        await utils.safe_wrap(lambda: message.answer(texts.admin_added_error.format(contragent="поддержку")))


@dp.message_handler(Text(equals=buttons.superadmin_remove_admin), state=TelegramState.superadmin_start)
@dp.message_handler(Text(equals=buttons.admin_remove_support), state=TelegramState.superadmin_start)
async def admin_remove(message: types.Message):
    isSuperadmin = message.text == buttons.superadmin_remove_admin
    isSupport = message.text == buttons.admin_remove_support

    if isSuperadmin:
        count = await db.count_superadmin_peers(message.from_user.id)
        entities = await db.get_superadmin_peers(message.from_user.id) if count > 0 else []
    else:  # isSupport
        count = await db.count_support_users()
        entities = await db.get_support_users() if count > 0 else []

    if count > 0:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for entity in entities:
            label = (entity["username"] + " " if "username" in entity else "") + entity.get("phone", str(entity["id"]))
            markup.add(types.InlineKeyboardButton(label, callback_data=str(entity["id"])))
        markup.add(types.InlineKeyboardButton(buttons.back, callback_data="back"))

        if isSuperadmin:
            await TelegramState.superadmin_remove_admin.set()
        else:
            await TelegramState.support_remove.set()

        await utils.safe_wrap(lambda: message.answer(texts.admin_remove, reply_markup=markup))
    else:
        text = texts.superadmin_remove_empty if isSuperadmin else texts.admin_remove_support_empty
        await utils.safe_wrap(lambda: message.answer(text, reply_markup=markups.superadmin_start))

@dp.callback_query_handler(state=TelegramState.superadmin_remove_admin)
@dp.callback_query_handler(state=TelegramState.support_remove)
async def admin_remove_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    isSuperadmin = current_state == "TelegramState:superadmin_remove_admin"

    if callback_query.data == "back":
        # Both superadmin_remove_admin and support_remove are only reachable by superadmins
        await TelegramState.superadmin_start.set()
        await callback_query.answer("")
        await utils.safe_wrap(lambda: bot.send_message(callback_query.from_user.id, texts.superadmin_start, reply_markup=markups.superadmin_start))
        return

    search = { "id": int(callback_query.data) }
    if isSuperadmin:
        entity = await db.get_superadmin(search)
    else:  # support_remove
        entity = await db.get_support_user(search)

    if entity is not None:
        if isSuperadmin:
            await TelegramState.superadmin_remove_admin_confirm.set()
        else:
            await TelegramState.support_remove_confirm.set()

        await state.set_data(search)
        await callback_query.answer("")

        name = entity["username"] if "username" in entity else entity.get("phone", str(entity["id"]))
        contragent = "суперадмина" if isSuperadmin else "сотрудника поддержки"
        await utils.safe_wrap(lambda: bot.send_message(
            callback_query.from_user.id,
            texts.admin_remove_confirm.format(contragent=contragent, username=name),
            reply_markup=markups.confirm
        ))
    else:
        await utils.safe_wrap(lambda: bot.send_message(callback_query.from_user.id, texts.admin_remove_confirm_error))

@dp.message_handler(Text(equals=buttons.confirm), state=TelegramState.superadmin_remove_admin_confirm)
@dp.message_handler(Text(equals=buttons.confirm), state=TelegramState.support_remove_confirm)
async def admin_remove_confirmed(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    isSuperadminTarget = current_state == "TelegramState:superadmin_remove_admin_confirm"

    search = await state.get_data()
    if isSuperadminTarget:
        entity = await db.get_superadmin(search)
    else:  # support_remove_confirm
        entity = await db.get_support_user(search)

    # Both states are only reachable by superadmins
    await TelegramState.superadmin_start.set()

    if isSuperadminTarget:
        await db.remove_superadmin(search)
        contragent = "Суперадмин"
    else:
        await db.remove_support(search)
        contragent = "Поддержка"

    contragent_state = dp.current_state(chat=entity["id"], user=entity["id"])
    await contragent_state.finish()

    name = entity["username"] if "username" in entity else entity.get("phone", str(entity["id"]))
    await utils.safe_wrap(lambda: message.answer(
        texts.admin_removed.format(contragent=contragent, username=name),
        reply_markup=markups.superadmin_start
    ))


# =============================================================================
# Gamer — referral, account screen, wallet address
# =============================================================================

@dp.message_handler(Text(equals=buttons.referral), state=TelegramState.start)
async def gamer_referral_link(message: types.Message, state: FSMContext):
    me = await bot.get_me()
    referral_link = f'https://t.me/{me.username}?start={message.from_user.id}'

    await TelegramState.referral.set()
    sent_message = await utils.safe_wrap(lambda: message.answer(
        texts.gamer_referral_link.format(link=utils.escape(referral_link)),
        reply_markup=markups.back, parse_mode="MarkdownV2", disable_web_page_preview=True
    ))

    await utils.add_message_history(db, message)
    await utils.clean_messages(bot, db, message.from_user.id)
    await utils.add_message_history(db, sent_message)


@dp.message_handler(Text(equals=buttons.gamer_invite_friend, ignore_case=True),
                    state=TelegramState.start)
async def gamer_invite_link(message: types.Message):
    token = await db.ensure_invite_token(message.from_user.id, "gamer")
    link = f"t.me/{BOT_USERNAME}?start={token['uuid']}"
    await utils.add_message_history(db, message)
    await utils.clean_messages(bot, db, message.from_user.id)
    sent = await safe_wrap(lambda: message.answer(texts.invite_link.format(link=link), disable_web_page_preview=True))
    await utils.add_message_history(db, sent)


@dp.message_handler(Text(equals=buttons.account), state=TelegramState.start)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.address)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.change_address)
async def gamer_account(message: types.Message, state: FSMContext):
    gamer = await db.get_gamer(message.from_user.id)
    if not gamer:
        await utils.safe_wrap(lambda: message.answer(
            texts.gamer_start, reply_markup=markups.start,
            parse_mode="MarkdownV2", disable_web_page_preview=True
        ))
        return

    if "referral" in gamer and gamer["referral"]:
        referral_gamer = await db.get_gamer(gamer["referral"])
        referral = ("@" + referral_gamer["username"]) if referral_gamer is not None else "Админ"
    else:
        referral = "Нет"

    referral_count = await db.count_gamers({ "referral": message.from_user.id })

    # Season 3 points
    season_points = await db.get_gamer_season_points(gamer["_id"])

    balance = 'Залетай играть 😉'
    accounts_table = ''

    has_address = "address" in gamer and gamer["address"] is not None
    address = gamer["address"] if has_address else "*добавь адрес кошелька для выплат*"
    markup = markups.backaddresschange if has_address else markups.backaddressadd

    accounts = await db.get_gamer_accounts(gamer["_id"])
    accounts.sort(key=lambda a: a.get("tower", {}).get("points", 0), reverse=True)

    db_config = await db.get_config()
    support_handle = db_config.get("support_handle", "@goldalfsupp") if db_config else "@goldalfsupp"

    if len(accounts) > 0:
        balance = season_points

        for account in accounts:
            history = account.get("progress_history", [])
            last_delta = history[-1]["delta"] if history else 0
            status_emoji = {"active": "✅", "escalated": "🚨", "released": "🔓", "inactive": "⛔", "pending_release": "⏳"}.get(account.get("status", "active"), "✅")
            accounts_table += f'''\n{utils.escape('---------------------------')}\n
{status_emoji} *{utils.escape(account["profile"])}*
Tower Points: {account["tower"]["points"]} \\(\\+{last_delta} за последний синк\\)
Tower Rank: {account["tower"]["rank"]} \\| Floor: {account["tower"]["floor"]}

Account:
    Login: `{utils.escape(account["login"])}`
    Password: `{utils.escape(account["password"])}`

Proxy:
    Host: `{utils.escape(account["proxy"].get("host", ""))}`
    Port: `{account["proxy"].get("port", "")}`
    Login: `{utils.escape(account["proxy"].get("login", ""))}`
    Password: `{utils.escape(account["proxy"].get("password", ""))}`\n'''

    await TelegramState.account.set()
    sent_message = await utils.safe_wrap(lambda: message.answer(
        texts.gamer_account.format(
            address=address,
            referral=utils.escape(referral),
            referral_count=referral_count,
            balance=balance,
            accounts_table=accounts_table,
            support_handle=utils.escape(support_handle)
        ),
        reply_markup=markup,
        parse_mode="MarkdownV2"
    ))

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
        sent_message = await utils.safe_wrap(lambda: message.answer(
            texts.gamer_address_wrong, reply_markup=markups.back, parse_mode="MarkdownV2"
        ))
        await utils.add_message_history(db, sent_message)


# =============================================================================
# Gamer — pick up account (Season 4: instant auto-assign)
# =============================================================================

@dp.message_handler(Text(equals=buttons.pickup_account), state=TelegramState.start)
async def gamer_pickup_account(message: types.Message, state: FSMContext):
    gamer = await db.get_gamer(message.from_user.id)
    if not gamer:
        return
    db_config = await db.get_config()

    eligible, reason = await db.check_assignment_eligibility(gamer["_id"], db_config)

    await utils.add_message_history(db, message)

    if not eligible:
        sent = await utils.safe_wrap(lambda: message.answer(
            texts.gamer_pickup_ineligible.format(reason=utils.escape(reason)),
            reply_markup=markups.start, parse_mode="MarkdownV2"
        ))
        await utils.clean_messages(bot, db, message.from_user.id)
        await utils.add_message_history(db, sent)
        return

    account = await db.pickup_account(gamer["_id"])

    if account is None:
        sent = await utils.safe_wrap(lambda: message.answer(
            texts.gamer_pickup_no_accounts, reply_markup=markups.start, parse_mode="MarkdownV2"
        ))
        await utils.clean_messages(bot, db, message.from_user.id)
        await utils.add_message_history(db, sent)
        return

    await db.mark_gamer_season_active(gamer["_id"])

    sent = await utils.safe_wrap(lambda: message.answer(
        texts.gamer_pickup_success.format(
            profile=utils.escape(account["profile"]),
            login=utils.escape(account.get("login", "")),
            password=utils.escape(account.get("password", "")),
        ),
        reply_markup=markups.start, parse_mode="MarkdownV2"
    ))
    await utils.clean_messages(bot, db, message.from_user.id)
    await utils.add_message_history(db, sent)


# =============================================================================
# Gamer — on-demand account release
# =============================================================================

@dp.message_handler(Text(equals=buttons.release_account), state=TelegramState.start)
async def gamer_release_account_prompt(message: types.Message, state: FSMContext):
    gamer = await db.get_gamer(message.from_user.id)
    if not gamer:
        return
    accounts = await db.get_gamer_accounts(gamer["_id"])

    # Only offer accounts that are strictly active (not already escalated/pending)
    releasable = [a for a in accounts if a.get("status") == "active"]

    await utils.add_message_history(db, message)

    if not releasable:
        sent = await utils.safe_wrap(lambda: message.answer(
            texts.gamer_release_account_no_accounts,
            reply_markup=markups.start, parse_mode="MarkdownV2"
        ))
        await utils.clean_messages(bot, db, message.from_user.id)
        await utils.add_message_history(db, sent)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for account in releasable:
        history = account.get("progress_history", [])
        last_delta = history[-1]["delta"] if history else 0
        label = f"{account['profile']}  (башня: {account['tower']['points']}, +{last_delta} за синк)"
        # Use _id hex (24 chars) — profile names can exceed Telegram's 64-byte callback_data limit
        markup.add(types.InlineKeyboardButton(label, callback_data=f"release_select:{account['_id']}"))
    markup.add(types.InlineKeyboardButton(buttons.back, callback_data="release_back"))

    await TelegramState.gamer_release_account.set()
    sent = await utils.safe_wrap(lambda: message.answer(
        texts.gamer_release_account_prompt, reply_markup=markup, parse_mode="MarkdownV2"
    ))
    await utils.clean_messages(bot, db, message.from_user.id)
    await utils.add_message_history(db, sent)


@dp.callback_query_handler(lambda c: c.data and (c.data.startswith("release_select:") or c.data == "release_back"), state=TelegramState.gamer_release_account)
async def gamer_release_account_select(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer("")  # MUST be first

    if callback_query.data == "release_back":
        await TelegramState.start.set()
        await utils.safe_wrap(lambda: bot.send_message(
            callback_query.from_user.id, texts.gamer_start,
            reply_markup=markups.start, parse_mode="MarkdownV2", disable_web_page_preview=True
        ))
        return

    account_oid_str = callback_query.data.split(":", 1)[1]
    gamer = await db.get_gamer(callback_query.from_user.id)
    if not gamer:
        await TelegramState.start.set()
        return

    account = await db.get_account_by_object_id(ObjectId(account_oid_str))
    if not account:
        await TelegramState.start.set()
        return

    profile = account["profile"]

    result = await db.request_account_release(profile, gamer["_id"])
    if result.modified_count == 0:
        await TelegramState.start.set()
        return

    # Trigger explicit sync to capture final points before ownership ends
    try:
        await synchonizer.sync_single_account(profile)
    except Exception:
        pass

    # Re-fetch to get latest state for history display
    account = await db.get_account(profile)

    # Filter progress history to this gamer's own entries only
    all_history = account.get("progress_history", [])
    gamer_history = [e for e in all_history if e.get("gamer_id") == gamer["_id"]]
    last_entries = gamer_history[-5:] if len(gamer_history) >= 5 else gamer_history
    _lines = []
    for e in last_entries:
        date  = utils.escape(e['synced_at'].strftime('%d.%m %H:%M'))
        tower = utils.escape(str(e['tower_points']))
        sign  = utils.escape('+') if e['delta'] >= 0 else ''
        delta = utils.escape(str(e['delta']))
        _lines.append(f"{date} → {tower} \\({sign}{delta}\\)")
    history_lines = "\n".join(_lines) or "_нет данных_"

    release_text = texts.support_release_request.format(
        profile=utils.escape(profile),
        username=utils.escape(gamer.get("username", "???")),
        history=history_lines
    )

    # 3-button keyboard for support — on-demand release has deny option
    support_markup = types.InlineKeyboardMarkup(row_width=1)
    support_markup.add(
        types.InlineKeyboardButton(buttons.release_pool,   callback_data=f"release_pool:{account_oid_str}"),
        types.InlineKeyboardButton(buttons.release_finish, callback_data=f"release_finish:{account_oid_str}"),
        types.InlineKeyboardButton(buttons.release_deny,   callback_data=f"release_deny:{account_oid_str}"),
    )

    support_users = await db.get_support_users()
    for su in support_users:
        try:
            await utils.safe_wrap(lambda su=su: bot.send_message(
                su["id"], release_text, reply_markup=support_markup, parse_mode="MarkdownV2"
            ))
        except Exception:
            continue

    await TelegramState.start.set()
    await utils.safe_wrap(lambda: bot.send_message(
        callback_query.from_user.id,
        texts.gamer_release_account_sent.format(profile=utils.escape(profile)),
        reply_markup=markups.start, parse_mode="MarkdownV2"
    ))


# =============================================================================
# Support — on-demand release decisions (pool / finish / deny)
#           and inactivity escalation decisions (pool / finish)
# =============================================================================

@dp.callback_query_handler(
    lambda c: c.data and any(
        c.data.startswith(p) for p in ("release_pool:", "release_finish:", "release_deny:")
    ),
    state="*"
)
async def support_release_decision(callback_query: types.CallbackQuery):
    await callback_query.answer("")  # MUST be first

    if not await db.is_support(callback_query.from_user.id):
        await utils.safe_wrap(lambda: bot.send_message(
            callback_query.from_user.id, "Нет доступа", parse_mode="MarkdownV2"
        ))
        return

    action, account_oid_str = callback_query.data.split(":", 1)
    account = await db.get_account_by_object_id(ObjectId(account_oid_str))

    # deny is only valid for on-demand releases; pool/finish work for both pending_release and escalated
    valid_statuses = ["pending_release"] if action == "release_deny" else ["pending_release", "escalated"]

    if not account or account.get("status") not in valid_statuses:
        await utils.safe_wrap(lambda: bot.send_message(
            callback_query.from_user.id, "Запрос уже обработан", parse_mode="MarkdownV2"
        ))
        return

    profile = account["profile"]
    now = datetime.utcnow()
    gamer_id = account.get("gamer_id")
    gamer = await db.get_gamer_by_id(gamer_id) if gamer_id else None

    if action == "release_pool":
        release_reason = account.get("release_request", {}).get("type", "inactivity") if account.get("release_request") else "inactivity"
        await db.add_release_block(account["_id"], gamer_id, release_reason)
        new_count = await db.increment_pool_release_count(gamer_id)
        await db.release_account(profile, "released", released_at=now)
        if gamer and "id" in gamer:
            if new_count >= 5:
                await utils.safe_wrap(lambda: bot.send_message(
                    gamer["id"], texts.gamer_pickup_banned, parse_mode="MarkdownV2"
                ))
            await utils.safe_wrap(lambda: bot.send_message(
                gamer["id"],
                texts.gamer_release_account_pool_approved.format(profile=utils.escape(profile)),
                parse_mode="MarkdownV2"
            ))

    elif action == "release_finish":
        tower_points = account.get("tower", {}).get("points", 0)
        await db.finish_account(profile, callback_query.from_user.id, now, tower_points)
        if gamer and "id" in gamer:
            await utils.safe_wrap(lambda: bot.send_message(
                gamer["id"],
                texts.gamer_release_account_finished.format(profile=utils.escape(profile)),
                parse_mode="MarkdownV2"
            ))

    else:  # release_deny — on-demand only
        await db.set_account_status(profile, "active", extra_fields={"release_request": None})
        if gamer and "id" in gamer:
            await utils.safe_wrap(lambda: bot.send_message(
                gamer["id"],
                texts.gamer_release_account_denied.format(profile=utils.escape(profile)),
                parse_mode="MarkdownV2"
            ))

    await utils.safe_wrap(lambda: bot.send_message(
        callback_query.from_user.id,
        texts.support_release_decision_done.format(profile=utils.escape(profile)),
        parse_mode="MarkdownV2"
    ))


# =============================================================================
# Support / Superadmin — finished accounts list
# =============================================================================

@dp.message_handler(Text(equals=buttons.finished_accounts), state=TelegramState.support_start)
@dp.message_handler(Text(equals=buttons.finished_accounts), state=TelegramState.superadmin_start)
async def show_finished_accounts(message: types.Message, state: FSMContext):
    if await db.is_superadmin(message.from_user.id):
        home_markup = markups.superadmin_start
    else:
        home_markup = markups.support_start

    await utils.add_message_history(db, message)
    accounts = await db.get_finished_accounts()

    if not accounts:
        text = texts.support_finished_accounts_empty
    else:
        lines = [texts.support_finished_accounts_header]
        for acc in accounts:
            gamer_oid = acc.get("gamer_id")
            if not gamer_oid and acc.get("ownership_history"):
                gamer_oid = acc["ownership_history"][-1].get("gamer_id")
            gamer = await db.get_gamer_by_id(gamer_oid) if gamer_oid else None
            gamer_name = utils.escape(gamer.get("username", "???") if gamer else "???")
            profile = utils.escape(acc["profile"])
            finished_at = utils.escape(acc["finished_at"].strftime("%d.%m.%Y") if acc.get("finished_at") else "???")
            points = utils.escape(str(acc.get("final_tower_points", "?")))
            lines.append(texts.support_finished_accounts_item.format(
                profile=profile, gamer_username=gamer_name,
                finished_at=finished_at, points=points
            ))
        text = "".join(lines)

    await utils.clean_messages(bot, db, message.from_user.id)
    sent = await utils.safe_wrap(lambda: message.answer(
        text, reply_markup=home_markup, parse_mode="MarkdownV2"
    ))
    await utils.add_message_history(db, sent)


@dp.message_handler(Text(equals=buttons.support_invite_link, ignore_case=True),
                    state=TelegramState.support_start)
async def support_invite_link(message: types.Message):
    token = await db.ensure_invite_token(message.from_user.id, "support")
    link = f"t.me/{BOT_USERNAME}?start={token['uuid']}"
    await utils.add_message_history(db, message)
    await utils.clean_messages(bot, db, message.from_user.id)
    sent = await safe_wrap(lambda: message.answer(texts.invite_link.format(link=link), disable_web_page_preview=True))
    await utils.add_message_history(db, sent)


# =============================================================================
# Gamer — proof submission (any message while account is escalated)
# =============================================================================

@dp.message_handler(content_types=types.ContentType.ANY, state=TelegramState.start)
async def gamer_proof_submission(message: types.Message, state: FSMContext):
    """
    Catch-all for messages sent by a gamer on the home screen.
    If the gamer has an escalated account and hasn't sent proof yet, store the message as proof.
    """
    gamer = await db.get_gamer(message.from_user.id)
    if not gamer:
        return

    escalated = await db.get_accounts({
        "gamer_id": gamer["_id"],
        "status": "escalated",
        "pending_proof": None
    })

    if not escalated:
        return  # no escalated accounts needing proof — ignore message

    # Store proof for the first escalated account (one proof covers the case)
    account = escalated[0]
    await db.store_proof(account["profile"], message.from_user.id, message.message_id)

    # Forward proof to all support users immediately
    support_users = await db.get_support_users()
    for su in support_users:
        try:
            await utils.safe_wrap(lambda: bot.send_message(
                su["id"],
                f"📎 Доказательство от @{utils.escape(gamer.get('username', '???'))} для аккаунта *{utils.escape(account['profile'])}*:",
                parse_mode="MarkdownV2"
            ))
            await utils.safe_wrap(lambda: bot.forward_message(su["id"], message.from_user.id, message.message_id))
        except Exception:
            continue

    await utils.safe_wrap(lambda: message.answer(texts.gamer_proof_received))


# =============================================================================
# Support — decision callbacks
# =============================================================================

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("support_progress:"), state="*")
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("support_noprogress:"), state="*")
async def support_decision(callback_query: types.CallbackQuery):
    if not await db.is_support(callback_query.from_user.id):
        await callback_query.answer("Нет доступа")
        return

    action, account_oid_str = callback_query.data.split(":", 1)
    account = await db.get_account_by_object_id(ObjectId(account_oid_str))

    if not account or account.get("status") != "escalated":
        await callback_query.answer("Аккаунт уже обработан")
        return

    profile = account["profile"]
    now = datetime.utcnow()

    if action == "support_progress":
        # Progress possible: release account for reassignment
        new_status = "released"
    else:
        # No progress possible: mark inactive, not available for pickup
        new_status = "inactive"

    await db.release_account(profile, new_status, released_at=now)

    # Notify the gamer — different message depending on outcome
    gamer_id = account.get("gamer_id")
    if gamer_id:
        gamer = await db.get_gamer_by_id(gamer_id)
        if gamer and "id" in gamer:
            gamer_text = (
                texts.gamer_account_released if new_status == "released"
                else texts.gamer_account_inactive
            )
            await utils.safe_wrap(lambda: bot.send_message(
                gamer["id"],
                gamer_text.format(profile=utils.escape(profile)),
                parse_mode="MarkdownV2"
            ))

    await callback_query.answer("")
    await utils.safe_wrap(lambda: bot.send_message(
        callback_query.from_user.id,
        texts.support_decision_done.format(profile=utils.escape(profile)),
        parse_mode="MarkdownV2"
    ))


# =============================================================================
# Leaderboard — available to superadmin, support, and gamers
# =============================================================================

@dp.message_handler(Text(equals=buttons.leaderboard), state=TelegramState.superadmin_start)
@dp.message_handler(Text(equals=buttons.leaderboard), state=TelegramState.support_start)
@dp.message_handler(Text(equals=buttons.leaderboard), state=TelegramState.start)
async def leaderboard_handler(message: types.Message, state: FSMContext):
    await utils.add_message_history(db, message)

    season_entries = await db.get_all_gamers_season_points()

    # Batch-resolve all gamer ObjectIds in one query instead of N sequential lookups
    oids = [e["_id"] for e in season_entries if e["_id"] is not None]
    gamers_list = await db.db.gamers.find({"_id": {"$in": oids}}).to_list(None)
    oid_to_username = {g["_id"]: g["username"] for g in gamers_list if g.get("username")}

    leaderboard_data = [
        (oid_to_username[e["_id"]], e["total"])
        for e in season_entries
        if e["_id"] in oid_to_username
    ]

    await _print_leaderboard(message.from_user.id, leaderboard_data)


@dp.message_handler(Text(equals=buttons.back), state=TelegramState.leaderboard)
async def leaderboard_back(message: types.Message, state: FSMContext):
    await utils.add_message_history(db, message)
    await start(message, state)


async def _print_leaderboard(user_id: int, leaderboard_data: list):
    has_leaderboard = True

    db_config = await db.get_config()
    await TelegramState.leaderboard.set()

    gamer = await db.get_gamer(user_id)
    try:
        text = '👑 *Leaderboard* 👑\n\n'
        if gamer:
            gamer_index = next(i for i, d in enumerate(leaderboard_data) if d[0] == gamer["username"])
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

        for i, d in enumerate(visible_data):
            is_me = (i + start_index == gamer_index) and gamer
            text += (
                f'{"*" if is_me else ""}'
                f'{i + start_index + 1}\. '
                f'{"||Перефарми меня||" if (i + start_index < gamer_index and gamer) else utils.escape(f"@{d[0]}")}'
                f' {d[1]}'
                f' {"👑" if i == 0 and start_index == 0 else ""}'
                f'{"*" if is_me else ""}\n'
            )

        if end_index < len(leaderboard_data):
            text += '\.\.\.'

    except StopIteration:
        has_leaderboard = False

    sent_message = await utils.safe_wrap(lambda: bot.send_message(
        user_id,
        text if has_leaderboard else texts.gamer_no_leaderboard,
        reply_markup=markups.back,
        parse_mode="MarkdownV2"
    ))

    await utils.clean_messages(bot, db, user_id)
    await utils.add_message_history(db, sent_message)


# =============================================================================
# Global error boundary — prevents one bad update from crashing the process
# =============================================================================

@dp.errors_handler()
async def global_error_handler(update: types.Update, exception: Exception):
    """Catch-all: log the error and swallow it so the bot keeps running."""
    update_id = getattr(update, "update_id", "?")
    print(f"[ERROR] Update {update_id} — {type(exception).__name__}: {exception}")
    traceback.print_exc()
    return True  # returning True suppresses the exception


if __name__ == '__main__':
    print("Bot started")
    executor.start_polling(dp, skip_updates=False)
