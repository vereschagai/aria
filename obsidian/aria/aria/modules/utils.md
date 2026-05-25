# Module: utils.py

**Type:** Shared utilities  
**Lines:** 41

## Functions

### `escape(text: str) → str`
MarkdownV2 character escaping. Handles backslash first, then all Telegram special characters. Used everywhere a dynamic value is inserted into a MarkdownV2 message.

### `add_message_history(db, message, folder="default")`
Pushes a `message_id` to the DB message history for the given user and folder. Called before sending messages that will need cleanup on state transition.

### `clean_messages(bot, db, user_id, folder="default", last=0)`
Deletes all tracked messages for a user/folder from Telegram. Retries up to 5 times on `TelegramAPIError`. `last` param keeps the N most recent messages if > 0.

### `safe_wrap(corofn)`
`@retry(wait=wait_exponential(multiplier=1, min=1, max=60))` decorator. Wraps any coroutine with tenacity exponential backoff. Used for operations that may fail transiently.

## Dependencies

- [[modules/mongodb]] — `push_message_history()`, `get_message_history()`, `clean_message_history()`
- `tenacity` — exponential backoff
- aiogram `Bot`, `Message`
