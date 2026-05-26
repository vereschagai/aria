# Flow: Leaderboard

**Trigger:** Leaderboard button press in any role home state  
**Actor:** Any role (superadmin, admin, operator, support, gamer)  
**Handler:** `OperatorController.__leaderboard()` (line 53), `__print_leaderboard()` (line 72)

## Steps

```
1. User presses leaderboard button (available to all roles)
        ↓
2. operator_controller.__leaderboard() fires
   add_message_history
        ↓
3. db.get_all_gamers_season_points()
   Single MongoDB aggregation pipeline:
     $unwind: progress_history
     $match: {delta: {$gt: 0}, gamer_id: {$ne: null}}
     $group: {_id: "$gamer_id", total: {$sum: "$delta"}}
     $sort: {total: -1}
   Returns: [{_id: ObjectId, total: int}, ...]
        ↓
4. Batch resolve ObjectIds → usernames:
   db.gamers.find({"_id": {"$in": [all_oids]}})
   Build oid_to_username dict
   Build data = [(username, total), ...] for resolvable entries
        ↓
5. __print_leaderboard(user_id, data):
   db.get_config() → read leaderboard_gap
   TelegramState.leaderboard.set()

   db.get_gamer(user_id):
     None (non-gamer role) → show full leaderboard, start=0, end=len(data)
     Gamer found → find their rank via next(i for i, (u,_) in enumerate(data) if u == gamer.username)
       StopIteration (gamer has no points) → has_leaderboard = False

   If gamer found and on board:
     start_index = max(gamer_index - leaderboard_gap, 0)
     end_index = gamer_index + leaderboard_gap + 1
     Prepend "..." if start_index > 0
     Append "..." if end_index < len(data)

   For each visible entry:
     if index < gamer_index: show ||spoiler text|| (username hidden behind Telegram spoiler)
     if index == gamer_index: bold formatting
     if index == 0 and visible: 👑 emoji on rank 1

   send leaderboard text (or texts.gamer_no_leaderboard if not on board)
        + markups.back (MarkdownV2)
   clean_messages, add_message_history
        ↓
6. Back button from leaderboard:
   OperatorController.__main() fires → calls main(user_id)
   Re-runs full role resolution → sends appropriate home screen
```

## End State

`TelegramState.leaderboard`. User sees leaderboard. Back returns to role home.

## Scoring Rules

- Season points = Σ(positive `delta` values where `gamer_id == this_gamer`) across all accounts owned
- Syncs while account is in pool (`gamer_id: null`) are not attributed to anyone
- Points from released accounts are retained — attributed by ObjectId permanently

## Display Rules

- Non-gamer roles (operator, support, admin, superadmin): full list, all entries visible
- Gamers: `leaderboard_gap` entries above and below their rank
- Entries ranked above the gamer are hidden behind Telegram's spoiler formatting (`||text||`)
- Gamer not on board: `texts.gamer_no_leaderboard` message

## Performance

2 DB round-trips total regardless of guild size: one aggregation, one batch username lookup.

## Known Dead Code (fixed)

`is_new_year` parameter removed — was never passed as `True`. Crown emoji is now unconditional on rank 1.

## Modules
- [[modules/main]] — `__leaderboard`, `__print_leaderboard` (moved from operator_controller in Sprint A)
- [[modules/mongodb]] — `get_all_gamers_season_points`, `get_gamers`, `get_gamer`, `get_config`
- [[modules/texts]] — `gamer_no_leaderboard`
- [[modules/markups]] — `back`
- [[modules/state]] — `TelegramState.leaderboard`
- [[modules/utils]] — `clean_messages`, `add_message_history`
