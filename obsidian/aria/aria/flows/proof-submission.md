# Flow: Proof Submission

**Trigger:** Any message sent by a gamer in `TelegramState.start` that doesn't match any registered button  
**Actor:** Gamer (with at least one escalated account)  
**Handler:** `gamer_proof_submission()` — main.py line 816 (catch-all, runs last for `TelegramState.start`)

## Steps

```
1. Gamer sends any message (text, photo, video, etc.) from the home screen
        ↓
2. No registered button handler matched → catch-all fires
        ↓
3. db.get_gamer(message.from_user.id)
   If None → return silently
        ↓
4. db.get_accounts({
     "gamer_id": gamer["_id"],
     "status": "escalated",
     "pending_proof": None         ← only accounts that don't yet have proof
   })
   If empty → return silently (message is dropped)
        ↓
5. Take escalated[0] (first escalated account needing proof)
        ↓
6. db.store_proof(account["profile"], message.from_user.id, message.message_id)
   Writes pending_proof = {submitted_at, message_id, chat_id} to account doc
        ↓
7. db.get_support_users()
   For each support user:
     send header: "📎 Доказательство от @{username} для аккаунта {profile}:"
     bot.forward_message(su["id"], message.from_user.id, message.message_id)
     errors caught per-user (try/except, logged, continue)
        ↓
8. send texts.gamer_proof_received to gamer
```

## End State

`TelegramState.start`. Gamer receives a confirmation. Support users receive the forwarded proof. Account `pending_proof` field is set.

## How Proof Is Used Downstream

When `progress_monitor._escalate()` fires later, it checks for `pending_proof` on the account and forwards it to support users again alongside the escalation card. See [[flows/inactivity-escalation]].

## Edge Cases

- **Only the first escalated-without-proof account** gets the proof. If a gamer has multiple escalated accounts, each separate message they send goes to the one with the oldest pending escalation.
- Once `pending_proof` is set on an account, that account is excluded from the `pending_proof: None` filter — subsequent messages target the next escalated account (if any).
- Any random message in `TelegramState.start` that doesn't match a button reaches this handler — if the gamer has no escalated accounts, the message is silently ignored. This can be confusing for gamers who send unrelated messages.
- If a support user has blocked the bot, their proof forwarding fails silently (caught in per-user try/except).

## Modules

- [[modules/main]] — handler
- [[modules/mongodb]] — `get_gamer`, `get_accounts`, `store_proof`, `get_support_users`
- [[modules/texts]] — `gamer_proof_received`
- [[modules/utils]] — forwarding via `bot.forward_message`
