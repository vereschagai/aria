import string
import random
import math

from aiogram import Bot
from aiogram.types import Message
from aiogram.utils.exceptions import TelegramAPIError

from tenacity import retry, wait_exponential

from mongodb import MongoDb

password_alphabet = string.ascii_letters + string.digits + string.punctuation

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

    

def make_sandbox_url(location):
    return f'sandboxlauncher://?lexp={location}&env=prod&product=gc'

def make_launcher_url(id, host, port):
    return f'shirefarmlauncher://?launch={id}&host={host}&port={port}'

def make_uploader_url(id, host, port):
    return f'shirefarmlauncher://?upload={id}&host={host}&port={port}'


def format_minutes(minutes):
    suffix = "минут" if minutes == 0 or minutes > 4 and minutes % 100 < 21 else ("минута" if minutes % 10 == 1 else "минуты" if minutes % 10 > 1 and minutes % 10 < 5 else "минут")
    return f'{minutes} {suffix}'

def format_points(points):
    suffix = "баллов" if points == 0 or points > 4 and points % 100 < 21 else ("балл" if points % 10 == 1 else "балла" if points % 10 > 1 and points % 10 < 5 else "баллов")
    return f'{points} {suffix}'

def generate_int(digits):
    return random.randint(math.pow(10, digits - 1), math.pow(10, digits))

@retry(wait=wait_exponential(multiplier=1, min=1, max=60))
async def safe_wrap(corofn):
    return await corofn()

