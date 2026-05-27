from datetime import datetime
from uuid import uuid4

from typing import Optional

from bson import ObjectId
from pymongo import DESCENDING, ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError
import motor.motor_asyncio


class MongoDb:
    def __init__(self, host, port, db_name, username, password):
        self.connection = motor.motor_asyncio.AsyncIOMotorClient('mongodb://%s:%s@%s:%s/?authSource=admin' % (username, password, host, port) if username and password else 'mongodb://%s:%s' % (host, port))
        self.db : motor.motor_asyncio.AsyncIOMotorDatabase = self.connection[db_name]


    # -------------------------------------------------------------------------
    # Config
    # -------------------------------------------------------------------------

    async def get_config(self):
        return await self.db.config.find_one({})

    async def update_config(self, field, value):
        return await self.db.config.update_one({}, { "$set": { field: value } }, upsert=True)


    # -------------------------------------------------------------------------
    # Admins / superadmins
    # -------------------------------------------------------------------------

    async def is_superadmin(self, user_id):
        return await self.db.admin.find_one({ "id": user_id, "superadmin": True }) != None

    async def add_superadmin(self, admin):
        admin["superadmin"] = True
        return await self.db.admin.insert_one(admin)

    async def get_superadmin(self, search: dict):
        """Fetch a single superadmin document matching search."""
        search = {**search, "superadmin": True}
        return await self.db.admin.find_one(search)

    async def remove_superadmin(self, search: dict):
        """Delete a superadmin document matching search."""
        search = {**search, "superadmin": True}
        return await self.db.admin.delete_one(search)

    async def get_superadmin_peers(self, exclude_id: int):
        """All superadmins except the caller — used for the remove-superadmin list."""
        return await self.db.admin.find({ "superadmin": True, "id": { "$ne": exclude_id } }).to_list(None)

    async def count_superadmin_peers(self, exclude_id: int):
        return await self.db.admin.count_documents({ "superadmin": True, "id": { "$ne": exclude_id } })



    # -------------------------------------------------------------------------
    # Support
    # -------------------------------------------------------------------------

    async def get_support_users(self, search = {}):
        return await self.db.support.find(search).to_list(None)

    async def count_support_users(self, search = {}):
        return await self.db.support.count_documents(search)

    async def is_support(self, user_id):
        return await self.db.support.find_one({ "id": user_id }) != None

    async def get_support_user(self, search):
        return await self.db.support.find_one(search)

    async def add_support(self, contact):
        return await self.db.support.insert_one({ "id": contact.user_id, "phone": contact.phone_number })

    async def remove_support(self, search):
        return await self.db.support.delete_one(search)


    # -------------------------------------------------------------------------
    # Gamers
    # -------------------------------------------------------------------------

    async def is_gamer(self, search):
        return await self.db.gamers.find_one(search) != None

    async def count_gamers(self, search):
        return await self.db.gamers.count_documents(search)

    async def get_gamers(self, search, sort=None):
        return await self.db.gamers.find(search, sort=sort).to_list(None)

    async def get_gamer(self, user_id):
        return await self.db.gamers.find_one({ "id": user_id })

    async def get_gamer_by_id(self, object_id: ObjectId):
        """Fetch gamer by MongoDB _id (ObjectId)."""
        return await self.db.gamers.find_one({ "_id": object_id })

    async def add_gamer(self, id, username, referral, address = None):
        return await self.db.gamers.insert_one({ "id": id, "username": username, "referral": referral, "address": address })

    async def update_gamer(self, search, gamer):
        if "id" in gamer and "username" in search:
            await self.db.gamers.update_many({ "referral_name": search["username"] }, { "$set": { "referral": gamer["id"] }, "$unset": { "referral_name": "" } })

        return await self.db.gamers.update_one(search, { "$set": gamer })

    async def update_gamer_address(self, user_id, address):
        return await self.db.gamers.update_one({ "id": user_id }, { "$set": { "address": address } })

    async def get_all_gamers_season_points(self) -> list:
        """
        Returns [{_id: gamer_ObjectId, total: int}, ...] sorted by total descending.
        Used by the leaderboard — one aggregation over the accounts collection instead
        of N per-gamer queries.
        """
        pipeline = [
            { "$unwind": "$progress_history" },
            { "$match": {
                "progress_history.delta": { "$gt": 0 },
                "progress_history.gamer_id": { "$ne": None }
            }},
            { "$group": {
                "_id": "$progress_history.gamer_id",
                "total": { "$sum": "$progress_history.delta" }
            }},
            { "$sort": { "total": -1 } }
        ]
        return await self.db.accounts.aggregate(pipeline).to_list(None)

    async def get_gamer_season_points(self, gamer_object_id: ObjectId) -> int:
        """
        Sum all positive progress_history deltas attributed to this gamer across ALL accounts
        (both currently and previously owned). This is the Season 3 leaderboard score.
        """
        pipeline = [
            { "$unwind": "$progress_history" },
            { "$match": {
                "progress_history.gamer_id": gamer_object_id,
                "progress_history.delta": { "$gt": 0 }
            }},
            { "$group": {
                "_id": None,
                "total": { "$sum": "$progress_history.delta" }
            }}
        ]
        result = await self.db.accounts.aggregate(pipeline).to_list(None)
        return result[0]["total"] if result else 0


    # -------------------------------------------------------------------------
    # Accounts
    # -------------------------------------------------------------------------

    async def get_accounts(self, search = {}, sort = None):
        return await self.db.accounts.find(search, sort=sort).to_list(None)

    async def get_account(self, profile: str):
        return await self.db.accounts.find_one({ "profile": profile })

    async def get_account_by_object_id(self, object_id: ObjectId):
        """Fetch account by MongoDB _id — used in callback handlers to avoid 64-byte limit."""
        return await self.db.accounts.find_one({ "_id": object_id })

    async def put_account(self, profile, data, upsert = True):
        return await self.db.accounts.update_one({ "profile": profile }, { "$set": data }, upsert=upsert)

    async def push_progress_entry(self, profile: str, entry: dict):
        """Append one entry to progress_history."""
        return await self.db.accounts.update_one(
            { "profile": profile },
            { "$push": { "progress_history": entry } }
        )

    async def get_gamer_accounts(self, gamer_object_id: ObjectId):
        """All accounts currently assigned to this gamer."""
        return await self.db.accounts.find({ "gamer_id": gamer_object_id }).to_list(None)

    async def count_gamer_accounts(self, gamer_object_id: ObjectId) -> int:
        return await self.db.accounts.count_documents({ "gamer_id": gamer_object_id, "status": "active" })

    async def get_active_assigned_accounts(self):
        """All accounts with an active owner (for inactivity checks)."""
        return await self.db.accounts.find({
            "gamer_id": { "$ne": None },
            "status": "active"
        }).to_list(None)

    async def get_escalated_accounts(self):
        return await self.db.accounts.find({ "status": "escalated" }).to_list(None)

    async def set_account_status(self, profile: str, status: str, extra_fields: dict = None):
        set_fields = {"status": status}
        unset_fields = {}
        if extra_fields:
            for k, v in extra_fields.items():
                if v is None:
                    unset_fields[k] = ""
                else:
                    set_fields[k] = v
        update = {"$set": set_fields}
        if unset_fields:
            update["$unset"] = unset_fields
        return await self.db.accounts.update_one({"profile": profile}, update)

    async def release_account(self, profile: str, status: str, released_at: datetime):
        """
        Close current ownership, clear gamer_id, set status.
        status is either 'released' (open for pickup) or 'inactive' (closed).
        pending_proof and release_request are fully removed ($unset) on release.
        """
        return await self.db.accounts.update_one(
            {"profile": profile, "ownership_history.released_at": None},
            {
                "$set": {
                    "status": status,
                    "gamer_id": None,
                    "escalated_at": None,
                    "ownership_history.$[last].released_at": released_at,
                },
                "$unset": {
                    "pending_proof": "",
                    "release_request": "",
                },
            },
            array_filters=[{"last.released_at": None}]
        )

    async def store_proof(self, profile: str, gamer_tg_id: int, message_id: int):
        """Store a gamer's proof message reference on the account."""
        return await self.db.accounts.update_one(
            { "profile": profile },
            { "$set": {
                "pending_proof": {
                    "submitted_at": datetime.utcnow(),
                    "message_id": message_id,
                    "chat_id": gamer_tg_id
                }
            }}
        )

    async def request_account_release(self, profile: str, gamer_object_id: ObjectId):
        """
        Mark an account as pending_release (gamer-initiated).
        The account remains assigned to the gamer until support decides.
        """
        return await self.db.accounts.update_one(
            { "profile": profile, "gamer_id": gamer_object_id, "status": "active" },
            { "$set": {
                "status": "pending_release",
                "release_request": {
                    "type": "on_demand",
                    "requested_at": datetime.utcnow(),
                    "gamer_id": gamer_object_id,
                }
            }}
        )

    async def check_assignment_eligibility(self, gamer_object_id: ObjectId, config: dict):
        """
        Returns (eligible: bool, reason: str).
        Gamer is eligible for a new account when:
          1. pool_release_count < 5 (not banned from pickup)
          2. Total occupied slots (active + escalated + pending_release) < max_accounts_per_gamer
          3. All strictly active accounts: last progress_history entry belongs to this gamer
             AND delta >= min_progress_points. Escalated/pending_release are exempt.
        """
        gamer = await self.db.gamers.find_one({"_id": gamer_object_id})
        if gamer and gamer.get("pool_release_count", 0) >= 5:
            return False, "Вы освободили слишком много аккаунтов. Взять новый нельзя."

        occupied_accounts = await self.db.accounts.find({
            "gamer_id": gamer_object_id,
            "status": {"$in": ["active", "escalated", "pending_release"]}
        }).to_list(None)

        max_accounts = config.get("max_accounts_per_gamer", 10)
        if len(occupied_accounts) >= max_accounts:
            return False, f"Достигнут лимит аккаунтов ({max_accounts})"

        min_progress = config.get("min_progress_points", 50)
        for account in occupied_accounts:
            if account["status"] != "active":
                continue
            history = account.get("progress_history", [])
            if not history:
                return False, f"Аккаунт {account['profile']} — нет данных о прогрессе"
            last = history[-1]
            if last.get("gamer_id") != gamer_object_id:
                return False, f"Аккаунт {account['profile']} — ожидаем синхронизацию под вашим владением"
            if last.get("delta", 0) < min_progress:
                return False, f"Аккаунт {account['profile']} — недостаточно прогресса (нужно {min_progress}+ очков башни)"

        return True, "ok"

    async def pickup_account(self, gamer_object_id: ObjectId):
        """
        Atomically assign the best available account to this gamer.
        Priority 1: accounts previously owned by this gamer, highest tower.points first.
        Priority 2: remaining released accounts whose last owner hasn't picked up this season
                    (season_picked_up != True) or has no previous owner, highest points first.
        Returns the assigned account document or None if pool is empty.
        """
        now = datetime.utcnow()
        blocked_ids = await self.get_gamer_release_block_ids(gamer_object_id)

        p1 = await self.db.accounts.find({
            "status": "released",
            "ownership_history.gamer_id": gamer_object_id,
            "_id": {"$nin": blocked_ids},
        }).sort("tower.points", DESCENDING).to_list(None)

        p1_ids = {a["_id"] for a in p1}
        remaining = await self.db.accounts.find({
            "status": "released",
            "_id": {"$nin": list(p1_ids) + blocked_ids},
        }).to_list(None)

        prev_owner_ids = [
            acc["ownership_history"][-1]["gamer_id"]
            for acc in remaining
            if acc.get("ownership_history") and acc["ownership_history"][-1].get("gamer_id")
        ]

        active_owner_ids = set()
        if prev_owner_ids:
            active_owners = await self.db.gamers.find({
                "_id": {"$in": prev_owner_ids},
                "season_picked_up": True,
            }).to_list(None)
            active_owner_ids = {g["_id"] for g in active_owners}

        p2 = []
        for acc in remaining:
            oh = acc.get("ownership_history", [])
            last_owner_id = oh[-1]["gamer_id"] if oh and oh[-1].get("gamer_id") else None
            if last_owner_id is None or last_owner_id not in active_owner_ids:
                p2.append(acc)
        p2.sort(key=lambda a: a.get("tower", {}).get("points", 0), reverse=True)

        for account in p1 + p2:
            result = await self.db.accounts.find_one_and_update(
                {"_id": account["_id"], "status": "released"},
                {
                    "$set": {
                        "gamer_id": gamer_object_id,
                        "status": "active",
                        "last_notified_day": None,
                        "escalated_at": None,
                    },
                    "$push": {
                        "ownership_history": {
                            "gamer_id": gamer_object_id,
                            "assigned_at": now,
                            "released_at": None,
                        }
                    },
                },
                return_document=ReturnDocument.AFTER,
            )
            if result:
                return result

        return None

    async def mark_gamer_season_active(self, gamer_object_id: ObjectId):
        """Set season_picked_up=True on first pickup this season. Idempotent."""
        await self.db.gamers.update_one(
            {"_id": gamer_object_id},
            {"$set": {"season_picked_up": True}}
        )


    # -------------------------------------------------------------------------
    # Release blocks — permanent (account, gamer) block within a season
    # -------------------------------------------------------------------------

    async def add_release_block(self, account_id: ObjectId, gamer_id: ObjectId, reason: str):
        """Upsert (account_id, gamer_id) pair into release_blocks. Silently ignores duplicate."""
        try:
            await self.db.release_blocks.insert_one({
                "account_id": account_id,
                "gamer_id": gamer_id,
                "blocked_at": datetime.utcnow(),
                "reason": reason,
            })
        except Exception:
            pass  # duplicate key = already blocked

    async def get_gamer_release_block_ids(self, gamer_id: ObjectId) -> list:
        """Return list of account ObjectIds this gamer is blocked from picking."""
        docs = await self.db.release_blocks.find(
            {"gamer_id": gamer_id}, {"account_id": 1}
        ).to_list(None)
        return [d["account_id"] for d in docs]

    async def increment_pool_release_count(self, gamer_id: ObjectId) -> int:
        """Increment pool_release_count for gamer. Returns the NEW count."""
        result = await self.db.gamers.find_one_and_update(
            {"_id": gamer_id},
            {"$inc": {"pool_release_count": 1}},
            return_document=ReturnDocument.AFTER,
            projection={"pool_release_count": 1},
        )
        return result.get("pool_release_count", 1) if result else 1

    async def finish_account(self, profile: str, support_id: int, now: datetime, tower_points: int):
        """Permanently close an account (status=finished). Clears gamer_id, removes release metadata."""
        # Close the open ownership entry (released_at: None) if one exists.
        # Separate call because array_filters requires the open-entry condition in the match,
        # which would make the second $set on top-level fields a no-op when already closed.
        await self.db.accounts.update_one(
            {"profile": profile, "ownership_history.released_at": None},
            {"$set": {"ownership_history.$[last].released_at": now}},
            array_filters=[{"last.released_at": None}],
        )
        await self.db.accounts.update_one(
            {"profile": profile},
            {
                "$set": {
                    "status": "finished",
                    "finished_at": now,
                    "finished_by": support_id,
                    "final_tower_points": tower_points,
                    "gamer_id": None,
                },
                "$unset": {"release_request": "", "escalated_at": ""},
            }
        )

    async def get_finished_accounts(self) -> list:
        """Return all finished accounts sorted by finished_at descending."""
        return await self.db.accounts.find(
            {"status": "finished"},
            {"profile": 1, "gamer_id": 1, "finished_at": 1, "finished_by": 1,
             "final_tower_points": 1, "ownership_history": 1}
        ).sort("finished_at", DESCENDING).to_list(None)

    # Invite tokens

    async def ensure_invite_token(self, issuer_id: int, role_type: str) -> dict:
        """Find token by issuer_id; create with uuid4 if missing. Always returns token doc."""
        existing = await self.db.invite_tokens.find_one({"issuer_id": issuer_id})
        if existing:
            return existing
        doc = {
            "uuid": str(uuid4()),
            "issuer_id": issuer_id,
            "role_type": role_type,
            "created_at": datetime.utcnow(),
        }
        try:
            await self.db.invite_tokens.insert_one(doc)
        except DuplicateKeyError:
            return await self.db.invite_tokens.find_one({"issuer_id": issuer_id})
        return doc

    async def get_invite_token_by_uuid(self, uuid_str: str) -> Optional[dict]:
        """Return token doc or None."""
        return await self.db.invite_tokens.find_one({"uuid": uuid_str})

    # -------------------------------------------------------------------------
    # Messages
    # -------------------------------------------------------------------------

    async def push_message_history(self, user_id, folder, message_id):
        return await self.db.messages.update_one({ "id": user_id }, { "$push": { folder: message_id } }, upsert=True)

    async def get_message_history(self, user_id, folder, last = 0):
        messages = await self.db.messages.find_one({ "id": user_id })
        history = messages[folder] if folder in messages else []

        if last > 0:
            return history[:-last]

        return history

    async def clean_message_history(self, user_id, folder, last = 0):
        new_history = []
        if last > 0:
            history = await self.get_message_history(user_id, folder)
            new_history = history[:-last]

        return await self.db.messages.update_one({ "id": user_id }, { "$set": { folder: new_history } })


    # -------------------------------------------------------------------------
    # Indexes
    # -------------------------------------------------------------------------

    async def ensure_indexes(self):
        # Role resolution — checked on every incoming message
        await self.db.admin.create_index([("id", ASCENDING), ("superadmin", ASCENDING)])
        await self.db.support.create_index("id", unique=True)

        # Gamers — high-frequency lookups and referral counts
        await self.db.gamers.create_index("id", unique=True)
        await self.db.gamers.create_index("username", sparse=True)
        await self.db.gamers.create_index("referral")
        await self.db.gamers.create_index("season_picked_up", sparse=True)

        # Accounts — profile upserts (sheet sync), gamer page, leaderboard sort, pickup priority
        await self.db.accounts.create_index("profile", unique=True)
        await self.db.accounts.create_index("gamer_id")
        await self.db.accounts.create_index("status")
        await self.db.accounts.create_index("last_progress_at")
        await self.db.accounts.create_index([("tower.points", DESCENDING)])
        await self.db.accounts.create_index([("progress_history.gamer_id", ASCENDING)])
        await self.db.accounts.create_index([("ownership_history.gamer_id", ASCENDING)])

        # Messages — read/written on every user interaction
        await self.db.messages.create_index("id", unique=True)

        # Release blocks — permanent per-season block for (account, gamer) pair
        await self.db.release_blocks.create_index(
            [("account_id", ASCENDING), ("gamer_id", ASCENDING)], unique=True
        )

        # invite_tokens: uuid (unique), issuer_id (unique)
        await self.db.invite_tokens.create_index("uuid", unique=True)
        await self.db.invite_tokens.create_index("issuer_id", unique=True)
