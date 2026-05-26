# NEXT — Pre-Launch Feature Sprint

> Last updated: 2026-05-26. Sprint A completed 2026-05-26. Full design rationale in [[memory/MEMORY]] session handoff.
>
> Execution order: Sprint A → B → C → D. Each sprint is independently deployable.
> Implementation workflow per task: brain-search → (design if feature) → implement → dry-test → code review → update docs → commit.

---

## Sprint A — Role Cleanup

Remove unused `admin` and `operator` roles entirely. Support inherits leaderboard.
**No DB migration needed** — neither collection was ever populated in production.

| # | Task | Files | Status |
|---|---|---|---|
| A1 | Delete `operator_controller.py`; remove import (line 25) and `operator_controller.init_handlers()` (line 926) from `main.py` | main.py, operator_controller.py | ✅ |
| A2 | Remove all operator FSM states from `state.py` (`operator_start`, `admin_add_operator`, `admin_remove_operator`, `admin_remove_operator_confirm`) | state.py | ✅ |
| A3 | Remove operator handlers from `main.py` (add operator ~line 266, remove operator ~line 337, operator_start handler ~line 97) | main.py | ✅ |
| A4 | Remove operator DB methods from `mongodb.py` (`is_operator`, `get_operator`, `get_operators`, `count_operators`, `add_operator`, `remove_operator`) | mongodb.py | ✅ |
| A5 | Remove admin FSM states from `state.py` (`admin_start`, `admin_add_support`, `admin_remove_support`, `admin_remove_admin`, `admin_remove_admin_confirm`) | state.py | ✅ |
| A6 | Remove admin handlers from `main.py` (admin_start branch ~line 115, all admin-state handlers) | main.py | ✅ |
| A7 | Remove admin DB methods from `mongodb.py` (`is_admin`, `get_admin`, `add_admin`, `remove_admin`) | mongodb.py | ✅ |
| A8 | Remove admin/operator strings, buttons, markups (`admin_start`, `admin_add_operator`, `admin_remove_operator`, `operator_start`, etc.) | texts.py, buttons.py, markups.py | ✅ |
| A9 | Extract leaderboard function from `operator_controller.py` → standalone helper; wire to support home screen with "🏆 Лидерборд" button | main.py, buttons.py, markups.py | ✅ |
| A10 | Update role resolution in `start()` — remove admin/operator branches; new order: superadmin → support → gamer | main.py | ✅ |

---

## Sprint B — Invite Token System

Replace raw Telegram IDs in `?start=` links with persistent UUID tokens stored in MongoDB.
Each inviter (superadmin, support, gamer) has exactly one token. Referral attribution goes to the token's issuer regardless of role.

**New collection:** `invite_tokens { uuid: String (unique), issuer_id: Int, role_type: "superadmin"|"support"|"gamer", created_at: DateTime }`

| # | Task | Files | Status |
|---|---|---|---|
| B1 | Add `invite_tokens` collection index (`uuid` unique) to `ensure_indexes()` | mongodb.py | ⬜ |
| B2 | Add MongoDb methods: `ensure_invite_token(issuer_id, role_type)` (get-or-create), `get_invite_token_by_uuid(uuid)` | mongodb.py | ⬜ |
| B3 | On bot startup: call `ensure_invite_token(SUPERADMIN_ID, "superadmin")` to pre-generate superadmin token | main.py | ⬜ |
| B4 | Replace referral validity check (line 151) with UUID lookup: `token = await db.get_invite_token_by_uuid(parts[1])` → valid if token exists, `referral = token["issuer_id"]` | main.py | ⬜ |
| B5 | Superadmin home: add "🔗 Ссылка для приглашения" button → handler fetches token UUID, replies with `t.me/<bot_username>?start=<uuid>` | main.py, buttons.py, markups.py, texts.py | ⬜ |
| B6 | In `add_support` flow: after `db.add_support(contact)`, call `ensure_invite_token(contact.user_id, "support")` | main.py | ⬜ |
| B7 | Support home: add "🔗 Пригласить игрока" button → same handler as B5 | main.py, buttons.py, markups.py, texts.py | ⬜ |
| B8 | Gamer home: add "👥 Пригласить друга" button → `ensure_invite_token(user_id, "gamer")` → reply with link + referral count | main.py, buttons.py, markups.py, texts.py | ⬜ |

---

## Sprint C — Chat Membership Gate

Optional: bot must be added to the guild's Telegram chat. Only members of that chat can join as gamers.
Config key: `required_chat_id` (null = gate disabled). Fails open if bot lacks permissions.

| # | Task | Files | Status |
|---|---|---|---|
| C1 | Add `required_chat_id: null` to config seed in `config.py` | config.py | ⬜ |
| C2 | In gamer join flow (after token validation): if `config.required_chat_id` is set, call `bot.get_chat_member(chat_id, user_id)`; reject with `texts.gamer_not_in_chat` if status not in member/admin/creator; catch exceptions → fail open | main.py | ⬜ |
| C3 | Add `texts.gamer_not_in_chat` message | texts.py | ⬜ |
| C4 | Superadmin config screen: add "set required chat" entry — superadmin forwards any message from the target chat → bot extracts `chat_id` and stores in config | main.py, texts.py | ⬜ |

---

## Sprint D — Support Dashboard

Replace notification-only support UX with a recoverable central screen.
Shows all open escalations and release requests with inline action + direct contact buttons.

| # | Task | Files | Status |
|---|---|---|---|
| D1 | Add `get_open_support_tasks()` to MongoDb: single query for accounts with `status: {$in: ["escalated", "pending_release"]}`, populate gamer info via lookup | mongodb.py | ⬜ |
| D2 | Add `support_dashboard` FSM state to `state.py` | state.py | ⬜ |
| D3 | Build dashboard message: sections "🚨 Эскалации" and "⏳ Запросы на выход", each account as inline block with action buttons + "💬 DM" (`url: tg://user?id=<gamer_id>`) | main.py | ⬜ |
| D4 | Add "📋 Задачи" button to support home screen (`markups.support_start`); handler enters `support_dashboard` state | main.py, buttons.py, markups.py, texts.py | ⬜ |
| D5 | Wire dashboard action buttons to existing `support_decision` and `support_release_decision` callback handlers | main.py | ⬜ |
| D6 | Add "💬 DM" inline button to outbound escalation notification messages in `progress_monitor._escalate()` | progress_monitor.py | ⬜ |

---

## Completed

*(Move tasks here when done)*
