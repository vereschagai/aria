# Flow: Wallet Address Management

**Trigger:** "Add address" or "Change address" button in `TelegramState.account`  
**Actor:** Gamer  
**Handlers:** `gamer_add_address()` (line 563), `gamer_change_address()` (line 572), `gamer_new_address()` (line 581)

## Add Address Flow

```
1. Gamer presses "Add address" (markups.backaddressadd button)
        ↓
2. gamer_add_address()
   TelegramState.address.set()
   send texts.gamer_address + markups.back
   clean_messages, add_message_history
        ↓
3. Gamer types an EVM wallet address
        ↓
4. gamer_new_address() (handles both address and change_address states)
   add_message_history for incoming message
        ↓
5. EthereumAddress(message.text)  ← cryptoaddress==0.2.1 validation
   INVALID → send texts.gamer_address_wrong + markups.back
              stay in address state, gamer can retry
   VALID   → db.update_gamer_address(user_id, message.text)
              call gamer_account(message, state)  ← redirect to account screen
```

## Change Address Flow

```
1. Gamer presses "Change address" (markups.backaddresschange button)
        ↓
2. gamer_change_address()
   TelegramState.change_address.set()
   send texts.gamer_change_address + markups.back
   clean_messages, add_message_history
        ↓
3. Same as steps 3–5 above (gamer_new_address handles both states)
```

## Back Navigation

Back button in `address` or `change_address` states: registered to `gamer_account()` — returns to account screen without saving.

## End State

`TelegramState.account` after successful save. User sees updated address on account screen.

## Edge Cases

- Invalid address: stays in current state, can retry unlimited times
- No check for duplicate addresses (two gamers can have the same wallet)
- Validation is Ethereum address format only — no BSC checksum or network-specific check beyond that
- After update, `gamer_account()` is called directly (not via redirect), so account screen refreshes with new address

## Modules

- [[modules/main]] — handlers
- [[modules/mongodb]] — `update_gamer_address`
- [[modules/texts]] — `gamer_address`, `gamer_change_address`, `gamer_address_wrong`
- [[modules/markups]] — `back`
- [[modules/state]] — `TelegramState.address`, `TelegramState.change_address`
