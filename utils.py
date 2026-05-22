from aiogram import Bot
from aiogram.types import Message
from aiogram.utils.exceptions import TelegramAPIError

from tenacity import retry, wait_exponential

from mongodb import MongoDb

def escape(password):
    to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    new_password = password.replace("\\", "\\\\")

    for char in to_escape:
        new_password = new_password.replace(char, '\\' + char)

    return new_password

async def add_message_history(db: MongoDb, message: Message, folder = "default"):
    await db.push_message_history(message.chat.id, folder, message.message_id)

async def clean_messages(bot: Bot, db: MongoDb, user_id: int, folder = "default", last=0):
    async def delete_message(message_id, attempt = 0):
        try:
            success = await bot.delete_message(user_id, message_id)
            if not success and attempt < 5:
                return await delete_message(message_id, attempt + 1)
        except TelegramAPIError as error:
            print('delete_message error', str(error))

            if attempt < 5:
                return await delete_message(message_id, attempt + 1)

    message_ids = await db.get_message_history(user_id, folder, last)
    await db.clean_message_history(user_id, folder, last)

    for message_id in message_ids:
        await delete_message(message_id=message_id)

@retry(wait=wait_exponential(multiplier=1, min=1, max=60))
async def safe_wrap(corofn):
    return await corofn()
