# Flow: Superadmin Broadcast (Feed)

**Trigger:** "📢 Рассылка" button in `TelegramState.superadmin_start`  
**Actor:** Superadmin  
**Handlers:** `superadmin_feed()` (line 241), `superadmin_feed_send()` (line 246)

## Steps

```
1. Superadmin presses "📢 Рассылка"
        ↓
2. superadmin_feed()
   TelegramState.superadmin_feed.set()
   send texts.superadmin_feed + markups.back
        ↓
3a. Superadmin presses back:
    start() handler fires → role resolution → superadmin home
    (no message sent)

3b. Superadmin sends any message (content_types=ANY):
        ↓
4. superadmin_feed_send() fires
   db.get_gamers({}) → fetch all gamer documents
   For each gamer:
     if "id" in gamer:
       message.copy_to(gamer["id"])  ← copies message exactly (preserves media/formatting)
       wrapped in safe_wrap (exponential backoff on flood wait)
       errors caught per-gamer (try/except, continue)
        ↓
5. TelegramState.superadmin_start.set()
   send texts.superadmin_feed_sent + markups.superadmin_start
```

## End State

`TelegramState.superadmin_start`. Message delivered to all gamers with stored Telegram IDs.

## What Can Be Broadcast

Any Telegram content type: text, photo, video, document, sticker, audio, etc. `message.copy_to()` copies the message as-is.

## Edge Cases

- Gamers without a stored `id` field (registered via username before `id` was captured) are silently skipped
- No rate limiting beyond tenacity retries on flood wait — large guilds may hit Telegram's 30 messages/second global limit
- No preview or confirmation step before sending — pressing the broadcast message immediately sends to all gamers
- No per-gamer delivery tracking or retry count beyond `safe_wrap` retries

## Modules

- [[modules/main]] — handlers
- [[modules/mongodb]] — `get_gamers`
- [[modules/texts]] — `superadmin_feed`, `superadmin_feed_sent`
- [[modules/markups]] — `back`, `superadmin_start`
- [[modules/state]] — `TelegramState.superadmin_feed`
- [[modules/utils]] — `safe_wrap`
