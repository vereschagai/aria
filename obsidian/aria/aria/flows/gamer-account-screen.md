# Flow: Gamer Account Screen

**Trigger:** Button press `buttons.account` in `TelegramState.start`, OR back from `address` / `change_address`  
**Actor:** Gamer  
**Handler:** `gamer_account()` — main.py line 493

## Steps

```
1. Gamer presses "📋 Мои аккаунты" (or navigates back from address flow)
        ↓
2. db.get_gamer(user_id)
   If None → send texts.gamer_start + markups.start, return
        ↓
3. Fetch referral info:
   if gamer.referral → db.get_gamer(referral_id) → display referral username or "Админ"
   db.count_gamers({"referral": user_id}) → count of users this gamer referred
        ↓
4. db.get_gamer_season_points(gamer["_id"])
   MongoDB aggregation: unwind progress_history, filter delta > 0 AND gamer_id == oid, sum
        ↓
5. Determine markup:
   if gamer.address → markups.backaddresschange (has "Change address" button)
   else             → markups.backaddressadd    (has "Add address" button)
        ↓
6. db.get_gamer_accounts(gamer["_id"])
   All accounts where gamer_id == this gamer's ObjectId
   Sorted by tower.points DESC
        ↓
7. For each account: build table row with:
   - Status emoji (✅ active, ⏳ pending_release, 🚨 escalated, etc.)
   - Profile name
   - Tower stats (points, rank, floor)
   - Login / password (monospace)
   - Proxy details
   - Last delta from progress_history[-1]
        ↓
8. TelegramState.account.set()
   Send texts.gamer_account.format(
     address, referral_username, referral_count,
     balance (season_points or "Залетай играть 😉"),
     accounts_table
   ) + chosen markup (MarkdownV2)
   clean_messages, add_message_history
```

## What the Gamer Sees

- Their wallet address (or prompt to add one)
- Their referral username + how many they've referred
- Season score (total positive deltas attributed to them)
- Full credentials for every account they currently hold (all statuses)
- Per-account: status, tower height, login/password, proxy

## End State

`TelegramState.account`

## From This State

- Add/change wallet address → [[flows/wallet-management]]
- Pick up an account → [[flows/gamer-pickup]]
- Release an account → [[flows/on-demand-release]]
- Leaderboard → [[flows/leaderboard]]
- Back → `TelegramState.start` (gamer home)

## Edge Cases

- If no accounts: `accounts_table = ''` and `balance = 'Залетай играть 😉'`
- Escalated and `pending_release` accounts are shown with their status emoji — gamer can see them but not act on them from this screen
- If `proxy = {}` (no proxy configured), proxy fields display as empty strings
- `last_delta = 0` if `progress_history` is empty on any account

## Modules

- [[modules/main]] — handler
- [[modules/mongodb]] — `get_gamer`, `get_gamer_season_points`, `get_gamer_accounts`, `count_gamers`
- [[modules/texts]] — `gamer_account`
- [[modules/markups]] — `backaddressadd`, `backaddresschange`
- [[modules/utils]] — `escape`, `clean_messages`, `add_message_history`
