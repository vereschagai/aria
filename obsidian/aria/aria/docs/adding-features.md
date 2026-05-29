# Adding Features — Step-by-Step Guide

This guide walks through implementing a new feature end-to-end, following the exact patterns used throughout the codebase.

---

## Checklist

- [ ] Define FSM states in `state.py`
- [ ] Add button label constants to `buttons.py`
- [ ] Add markup(s) to `markups.py`
- [ ] Add message strings to `texts.py`
- [ ] Add MongoDB methods to `mongodb.py` (if new data needed)
- [ ] Register handlers in `main.py` or `OperatorController.init_handlers()`
- [ ] Test all state transitions, including Back/Cancel paths

---

## 1. FSM states (`state.py`)

Every screen or waiting state needs an entry here.

```python
class TelegramState(StatesGroup):
    # ... existing states ...
    my_new_feature = State()
    my_new_feature_confirm = State()
```

**Convention**: `<role>_<feature>` for role-specific states. States shared across roles (like `leaderboard`) have no role prefix.

---

## 2. Button labels (`buttons.py`)

```python
my_new_feature = "🚀 Новая фича"
my_new_feature_confirm = "✅ Подтвердить фичу"
```

These strings are matched exactly in `Text(equals=...)` handlers.

---

## 3. Markups (`markups.py`)

```python
from aiogram.types import ReplyKeyboardMarkup
import buttons

my_new_feature = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
my_new_feature.add(buttons.my_new_feature_confirm, buttons.cancel)
my_new_feature.add(buttons.back)
```

Use `ReplyKeyboardMarkup` for persistent menu buttons.  
Use `types.InlineKeyboardMarkup` for dynamic lists (e.g., choose from a list of operators).

---

## 4. Message strings (`texts.py`)

```python
my_new_feature_prompt = '''
Введи данные для новой фичи:
'''

my_new_feature_success = '''
Фича успешно активирована для {username}!
'''
```

**MarkdownV2 strings**: pre-escape all static special characters manually with `\`. Dynamic values must go through `utils.escape()` at call time.

---

## 5. MongoDB methods (`mongodb.py`)

Add methods to the `MongoDb` class:

```python
async def get_my_feature_data(self, user_id):
    return await self.db.my_collection.find_one({ "id": user_id })

async def set_my_feature_data(self, user_id, value):
    return await self.db.my_collection.update_one(
        { "id": user_id },
        { "$set": { "value": value } },
        upsert=True
    )
```

Add indexes in `ensure_indexes()` if this collection will be queried frequently.

---

## 6. Handler registration

### In `main.py` (for superadmin, admin, gamer flows)

```python
@dp.message_handler(Text(equals=buttons.my_new_feature), state=TelegramState.start)
async def my_new_feature_start(message: types.Message, state: FSMContext):
    await utils.add_message_history(db, message)
    await TelegramState.my_new_feature.set()

    sent = await utils.safe_wrap(lambda: message.answer(
        texts.my_new_feature_prompt,
        reply_markup=markups.my_new_feature
    ))
    await utils.clean_messages(bot, db, message.from_user.id)
    await utils.add_message_history(db, sent)


@dp.message_handler(Text(equals=buttons.my_new_feature_confirm), state=TelegramState.my_new_feature)
async def my_new_feature_confirmed(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await db.set_my_feature_data(message.from_user.id, data["some_value"])
    await state.reset_data()

    await TelegramState.start.set()
    sent = await utils.safe_wrap(lambda: message.answer(
        texts.my_new_feature_success.format(username=utils.escape(message.from_user.username)),
        reply_markup=markups.start,
        parse_mode="MarkdownV2"
    ))
    await utils.add_message_history(db, message)
    await utils.clean_messages(bot, db, message.from_user.id)
    await utils.add_message_history(db, sent)
```

### In `OperatorController.init_handlers()` (for operator-accessible features)

```python
def init_handlers(self):
    # ... existing registrations ...
    self.dp.register_message_handler(
        self.__my_new_feature,
        Text(buttons.my_new_feature),
        state=TelegramState.operator_start
    )
```

---

## 7. Multi-role handlers

If a button should work from multiple role screens, register it for each relevant state:

```python
self.dp.register_message_handler(self.__leaderboard, Text(buttons.leaderboard), state=TelegramState.operator_start)
self.dp.register_message_handler(self.__leaderboard, Text(buttons.leaderboard), state=TelegramState.superadmin_start)
self.dp.register_message_handler(self.__leaderboard, Text(buttons.leaderboard), state=TelegramState.admin_start)
self.dp.register_message_handler(self.__leaderboard, Text(buttons.leaderboard), state=TelegramState.start)
```

---

## 8. Always wire up Back/Cancel paths

Every new state must have a back path registered in the global `start()` handler at the top of `main.py`:

```python
@dp.message_handler(CommandStart(), state=TelegramState.my_new_feature)
@dp.message_handler(Text(equals=buttons.back), state=TelegramState.my_new_feature)
@dp.message_handler(Text(equals=buttons.cancel), state=TelegramState.my_new_feature_confirm)
async def start(message: types.Message, state: FSMContext):
    ...
```

Or add a dedicated back handler if navigating to a sub-screen rather than the home screen.

---

## Common mistakes to avoid

- Forgetting `await utils.safe_wrap(lambda: ...)` on any Telegram API call — transient errors will crash the handler silently.
- Forgetting `utils.escape()` on dynamic content in MarkdownV2 messages — Telegram will reject the message with a parse error.
- Forgetting `clean_messages` — old messages will pile up on the user's screen.
- Registering a handler after `operator_controller.init_handlers()` call in `main.py` — the init call is at the very bottom; add your handlers before it or inside the controller.
- Using `message.answer` instead of `bot.send_message` in contexts where you only have the user ID (e.g., callback query handlers) — use `bot.send_message(user_id, ...)` there.
