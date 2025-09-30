import math
from numpy import sort
from pymongo import DESCENDING, ASCENDING
from datetime import datetime, timedelta
import motor.motor_asyncio

from bson.objectid import ObjectId

class MongoDb:
    def __init__(self, host, port, db_name, username, password):
        self.connection = motor.motor_asyncio.AsyncIOMotorClient('mongodb://%s:%s@%s:%s/?authSource=admin' % (username, password, host, port) if username and password else 'mongodb://%s:%s' % (host, port))
        self.db : motor.motor_asyncio.AsyncIOMotorDatabase = self.connection[db_name]


    async def get_config(self):
        return await self.db.config.find_one({})

    async def update_config(self, field, value):
        return await self.db.config.update_one({}, { "$set": { field: value } }, upsert=True)


    async def is_superadmin(self, user_id):
        return await self.db.admin.find_one({ "id": user_id, "superadmin": True }) != None

    async def get_superadmins(self):
        return await self.db.admin.find({ "superadmin": True }).to_list(None)

    async def add_superadmin(self, admin):
        admin["superadmin"] = True
        return await self.db.admin.insert_one(admin)


    async def get_admins(self):
        return await self.db.admin.find({ "superadmin": False }).to_list(None)

    async def count_admins(self, search):
        search["superadmin"] = False
        return await self.db.admin.count_documents(search)

    async def is_admin(self, user_id):
        return await self.db.admin.find_one({ "id": user_id, "superadmin": False }) != None

    async def get_admin(self, search):
        search["superadmin"] = False
        return await self.db.admin.find_one(search)

    async def add_admin(self, contact):
        return await self.db.admin.insert_one({ "id": contact.user_id, "phone": contact.phone_number, "superadmin": False })

    async def remove_admin(self, search):
        search["superadmin"] = False
        return await self.db.admin.delete_one(search)


    async def get_operators(self, search = {}):
        return await self.db.operators.find(search).to_list(None)

    async def count_operators(self, search):
        return await self.db.operators.count_documents(search)

    async def is_operator(self, user_id):
        return await self.get_operator({ "id": user_id }) != None

    async def get_operator(self, search):
        return await self.db.operators.find_one(search)

    async def add_operator(self, contact):
        return await self.db.operators.insert_one({ "id": contact.user_id, "phone": contact.phone_number })

    async def remove_operator(self, search):
        return await self.db.operators.delete_one(search)


    async def get_payers(self, search):
        return await self.db.payers.find(search).to_list(None)

    async def count_payers(self, search):
        return await self.db.payers.count_documents(search)

    async def is_payer(self, user_id):
        return await self.get_payer({ "id": user_id }) != None

    async def get_payer(self, search):
        return await self.db.payers.find_one(search)

    async def add_payer(self, contact):
        return await self.db.payers.insert_one({ "id": contact.user_id, "phone": contact.phone_number })

    async def remove_payer(self, search):
        return await self.db.payers.delete_one(search)


    async def is_gamer(self, search):
        return await self.db.gamers.find_one(search) != None

    async def count_gamers(self, search):
        return await self.db.gamers.count_documents(search)

    async def get_gamers(self, search, sort=None):
        return await self.db.gamers.find(search, sort=sort).to_list(None)

    async def get_gamer(self, user_id):
        return await self.db.gamers.find_one({ "id": user_id })

    async def get_gamer_username(self, username):
        return await self.db.gamers.find_one({ "username": username })

    async def add_gamer(self, id, username, referral, address = None):
        return await self.db.gamers.insert_one({ "id": id, "username": username, "referral": referral, "address": address })

    async def update_gamer(self, search, gamer):
        if "id" in gamer and "username" in search:
            await self.db.gamers.update_many({ "referral_name": search["username"] }, { "$set": { "referral": gamer["id"] }, "$unset": { "referral_name": "" } })

        return await self.db.gamers.update_one(search, { "$set": gamer })

    async def update_gamer_address(self, user_id, address):
        return await self.db.gamers.update_one({ "id": user_id }, { "$set": { "address": address } })


    async def add_gamer_balance(self, user_id, value):
        await self.db.gamers.update_one({ "id": user_id }, { "$inc": { 'balance': value } }, upsert=True)

    async def add_pending_balance(self, user_id, value):
        await self.db.gamers.update_one({ "id": user_id }, { "$inc": { 'pending_balance': value } }, upsert=True)

    async def remove_pending_balance(self, user_id, value):
        await self.db.gamers.update_one({ "id": user_id }, { "$inc": { 'pending_balance': -value } }, upsert=True)
    
    async def get_gamers_challenge_special_leaderboard(self):
        return await self.db.gamers.find({ "$or": [ { "balance.8": { "$gt": 0 } }, { "balance.9": { "$gt": 0 } } ] }).to_list(None)



    async def get_balance(self, is_validator, user_id):
        document = "validator_balance" if is_validator else "balance"
        return await self.db[document].find_one({ "id": user_id })

    async def add_balance(self, is_validator, user_id, amount):
        document = "validator_balance" if is_validator else "balance"
        field = "amount" if is_validator else "account"
        return await self.db[document].update_one({ "id": user_id }, { "$set": { "id": user_id }, "$inc": { field: amount } }, upsert=True)

    async def add_balance_withdrawing(self, is_validator, user_id, amount):
        document = "validator_balance" if is_validator else "balance"
        return await self.db[document].update_one({ "id": user_id }, { "$set": { "id": user_id }, "$inc": { "withdrawing": amount } }, upsert=True)

    async def normalize_balance(self, is_validator, user_id, amount):
        document = "validator_balance" if is_validator else "balance"
        return await self.db[document].update_one({ "id": user_id }, { "$inc": { "withdrawal": amount, "withdrawing": -amount } })

    async def add_user_initial_balance(self, search, amount):
        return await self.db.balance.update_one(search, { "$set": search, "$inc": { "account": amount, "withdrawal": amount } }, upsert=True)

    async def add_user_initial_referral_balance(self, search, amount):
        return await self.db.balance.update_one(search, { "$set": search, "$inc": { "referral": amount, "withdrawal": amount } }, upsert=True)


    async def count_cards(self, search):
        return await self.db.withdrawal_card.count_documents(search)

    async def get_cards(self, search):
        return await self.db.withdrawal_card.find(search).to_list(None)

    async def add_card(self, user_id, card):
        return await self.db.withdrawal_card.insert_one({ "id": user_id, "card": card })


    async def add_withdrawal_request(self, user_id, amount, card):
        return await self.db.withdrawal_request.insert_one({ "id": user_id, "amount": amount, "card": card, "status": "pending", "date": datetime.now() })

    async def get_latest_withdrawal_request(self, user_id):
        return await self.db.withdrawal_request.find_one({ "id": user_id }, sort=[( '_id', DESCENDING )])

    async def count_payer_withdraw_requests(self):
        return await self.db.withdrawal_request.count_documents({ "status": "pending" })

    async def get_payer_withdraw_requests(self):
        return await self.db.withdrawal_request.find({ "status": "pending" }).to_list(None)

    async def get_payer_withdraw_request(self, search):
        return await self.db.withdrawal_request.find_one(search)

    async def payer_mark_withdraw_done(self, search):
        return await self.db.withdrawal_request.update_one(search, { "$set": { "status": "done" } })


    async def get_validators(self, search):
        return await self.db.validators.find(search).to_list(None)

    async def count_validators(self, search):
        return await self.db.validators.count_documents(search)

    async def is_validator(self, user_id):
        return await self.get_validator({ "id": user_id }) != None

    async def get_validator(self, search):
        return await self.db.validators.find_one(search)

    async def add_validator(self, contact):
        return await self.db.validators.insert_one({ "id": contact.user_id, "phone": contact.phone_number, "status": "idle" })

    async def remove_validator(self, search):
        return await self.db.validators.delete_one(search)

    async def set_validator_status(self, user_id, status):
        return await self.db.validators.update_one({ "id": user_id }, { "$set": { "status": status } })
    
    async def get_redirects(self, search = {}):
        return await self.db.redirects.find(search).to_list(None)

    async def put_redirect(self, redirect):
        return await self.db.redirects.update_one({ "url": redirect["url"] }, { "$set": redirect }, upsert=True)
    
    async def remove_redirect(self, url):
        return await self.db.redirects.delete_one({ "url": url })
    

    async def count_launches(self, search = {}):
        return await self.db.launches.count_documents(search)

    async def get_launches(self, search = {}, projection = {}):
        return await self.db.launches.find(search, projection=projection).to_list(None)
    
    async def get_launch(self, search = {}):
        return await self.db.launches.find_one(search)
    
    async def put_launch(self, launch):
        return await self.db.launches.update_one({ "id": launch["id"] }, { "$set": launch }, upsert=True)
    
    async def remove_launch(self, key):
        return await self.db.launches.update_one({ "id": key }, { "$set": { "active": False } })
        

    async def get_challenges(self, search = {}, sort = None):
        return await self.db.challenges.find(search, sort=sort).to_list(None)

    async def get_challenge(self, search):
        return await self.db.challenges.find_one(search)
    
    async def add_challenge(self, data):
        return await self.db.challenges.insert_one(data)
    
    async def put_challenge(self, search, data, upsert=True):
        return await self.db.challenges.update_one(search, { "$set": data }, upsert=upsert)
    
    async def unput_challenge(self, search, data, upsert=True):
        return await self.db.challenges.update_one(search, { "$unset": data }, upsert=upsert)
    
    async def get_best_challenges(self, account_id, limit_by_daily=False, daily=False):
        db_config = await self.get_config()
        account = await self.get_account({ "_id": account_id })

        return await self.db.challenges.aggregate([
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            { "$eq": [ "$active", True ] },
                            { ("$gt" if daily else "$lt"): [ "$daily_deadline", datetime.now() ] } if limit_by_daily else True
                        ]
                    }
                }
            },
            {
                "$addFields": {
                    "premium_key_idx": {
                        "$subtract": [
                            {
                                "$ceil": {
                                    "$divide": [
                                        {
                                            "$divide": [
                                                {"$subtract": ["$daily_deadline", db_config["start_time"]]},
                                                1000 * 60 * 60 * 24
                                            ]
                                        },
                                        7
                                    ]
                                }
                            },
                            1
                        ]
                    }
                }
            },
            {
                "$addFields": {
                    "has_premium_key": {
                        "$cond": [ { "$gt": [ len(account["stat"]["categoryKeysOwnership"]), "$premium_key_idx" ] }, { "$arrayElemAt": [ account["stat"]["categoryKeysOwnership"], "$premium_key_idx" ] }, False ]
                    } if "stat" in account and "categoryKeysOwnership" in account["stat"] else False
                }
            },
            {
                "$lookup": {
                    "from": "gamer_activities",
                    "let": {
                        "challenge_id": "$_id",
                        "challenge_min_points": "$min_points",
                        "challenge_has_premium_key": "$has_premium_key"
                    },
                    "pipeline": [
                        { "$match": { "$expr": { 
                            "$and": [
                                { "$eq": [ "$account_id", account_id ] },
                                { "$eq": [ "$challenge_id", "$$challenge_id" ] },
                                { "$eq": [ { "$type": "$chest_session_id" }, "missing" ] },
                                { "$ne": [ "$status", "repeat" ] }
                            ]
                        } } }, # If no points, then not success status, then account is busy for the challenge, then to prevent from passing we should fill with challenge min points
                        { "$group": { "_id": None, "total_points": { "$sum": { "$ifNull": [ "$points", { "$sum": [ { "$cond": [ "$$challenge_has_premium_key", db_config["premium_quest_points"], 0 ] }, "$$challenge_min_points" ] } ] } } } }, 
                        { "$project": { "_id": 0, "total_points": 1 } }
                    ],
                    "as": "success_activity_ids"
                }
            },
            {
                "$match": {
                    "$expr": {
                        "$lte": [
                            { "$arrayElemAt": [ "$success_activity_ids.total_points", 0 ] },
                            { "$max": [ { "$subtract": [ { "$sum": [ { "$cond": [ "$has_premium_key", db_config["premium_quest_points"], 0 ] }, "$min_points" ] }, db_config["play_min_points_diff"] ] }, 0 ] }
                        ]
                    }
                }
            },
            { "$sort": { "priority": ASCENDING }  },
            # { "$unset": "success_activity_ids" }
        ]).to_list(None)
    
    async def get_daily_challenges(self):
        return await self.db.challenges.find({ "active": True, "daily_deadline": { "$gt": datetime.now() } }, sort=[( "priority", ASCENDING )])
    
    async def move_challenge_priority(self, new_priority, old_priority=None):
        count_challenges = await self.db.challenges.count_documents({})
        if old_priority == None:
            old_priority = count_challenges

        if new_priority == old_priority:
            return

        (min_priority,max_priority,direction) = (max(new_priority, 1), min(old_priority, count_challenges),1) if old_priority > new_priority else (max(old_priority, 1), min(new_priority, count_challenges),-1)
        
        return await self.db.challenges.update_many({ "priority": { "$gte": min_priority, "$lte": max_priority } }, { "$inc": { "priority": direction } })


    async def count_gamer_activities(self, search):
        return await self.db.gamer_activities.count_documents(search)

    async def get_gamer_activities(self, search, projection = {}):
        return await self.db.gamer_activities.find(search, projection=projection).to_list(None)

    async def add_gamer_activity(self, data):
        return await self.db.gamer_activities.insert_one(data)

    async def play_gamer_activity(self, activity_id, launch_installer=None):
        return await self.db.gamer_activities.update_one({ "_id": activity_id }, { "$set": { "status": "playing", "started_at": datetime.now(), "updated_at": datetime.now() } | ({ "launch_installer": launch_installer } if launch_installer else {}) })
    
    async def success_gamer_activity(self, activity_id, length):
        return await self.db.gamer_activities.update_one({ "_id": activity_id }, { "$set": { "status": "success", "length": length, "updated_at": datetime.now() } })

    async def update_gamer_activity_status(self, activity_id, status):
        return await self.db.gamer_activities.update_one({ "_id": activity_id }, { "$set": { "status": status, "updated_at": datetime.now() } })
    
    async def update_gamer_activity_points(self, activity_id, points):
        return await self.db.gamer_activities.update_one({ "_id": activity_id }, { "$set": { "points": points, "updated_at": datetime.now() } })

    async def update_gamer_activity_image(self, activity_id, image):
        return await self.db.gamer_activities.update_one({ "_id": activity_id }, { "$set": { "image": image, "updated_at": datetime.now() } })

    async def set_gamer_activity_ready(self, activity_id):
        return await self.db.gamer_activities.update_one({ "_id": activity_id }, { "$set": { "user_ready": True, "updated_at": datetime.now() } })

    async def remove_gamer_activity(self, activity_id):
        return await self.db.gamer_activities.delete_one({ "_id": activity_id })

    async def get_gamer_activity(self, search, sort=None):
        return await self.db.gamer_activities.find_one(search, sort=sort)
    
    async def cancel_gamer_activity(self, activity_id):
        return await self.db.gamer_activities.update_one({ "_id": activity_id }, { "$set": { "status": "cancelled", "cancelled_at": datetime.now() } })
    
    async def count_already_points(self, challenge_id, account_id):
        return sum(activity["points"] for activity in await self.db.gamer_activities.find({ "status": "success", "chest_session_id": { "$exists": False }, "challenge_id": challenge_id, "account_id": account_id }).to_list(None))
    

    async def get_chest_sessions(self, search = {}):
        return await self.db.chest_sessions.find(search).to_list(None)

    async def get_chest_session(self, search = {}):
        return await self.db.chest_sessions.find_one(search)

    async def put_chest_session(self, search, data, upsert = True):
        return await self.db.chest_sessions.update_one(search, { "$set": data }, upsert=upsert)
    
    async def update_chest_session_status(self, session_id, status):
        return await self.db.chest_sessions.update_one({ "_id": session_id }, { "$set": { "status": status, "updated_at": datetime.now() } })
    

    async def get_claim_tasks(self, search = {}):
        return await self.db.claim_tasks.find(search).to_list(None)

    async def get_claim_task(self, search = {}):
        return await self.db.claim_tasks.find_one(search)

    async def put_claim_task(self, search, data, upsert = True):
        return await self.db.claim_tasks.update_one(search, { "$set": data }, upsert=upsert)
    
    async def update_claim_task_status(self, claim_task_id, status):
        return await self.db.claim_tasks.update_one({ "_id": claim_task_id }, { "$set": { "status": status, "updated_at": datetime.now() } })


    async def get_account(self, search):
        return await self.db.accounts.find_one(search)

    async def get_accounts(self, search = {}, sort = None):
        return await self.db.accounts.find(search, sort=sort).to_list(None)

    async def count_accounts(self, search = {}):
        return await self.db.accounts.count_documents(search)

    async def put_account(self, profile, data, upsert = True):
        return await self.db.accounts.update_one({ "profile": profile }, { "$set": data }, upsert=upsert)
    
    async def deactivate_account(self, search):
        return await self.db.accounts.update_one(search, { "$set": { "active": False }})


    async def get_failed_tasks(self):
        return await self.db.failed_tasks.find({}).to_list(None)

    async def add_failed_tasks(self, tasks):
        return await self.db.failed_tasks.insert_many(tasks)

    async def add_failed_task(self, task_id, start_at = None):
        failed = {
            "id": task_id
        } | ({ "start_at": start_at } if start_at != None else {})
        
        return await self.db.failed_tasks.insert_one(failed)

    async def remove_failed_task(self, task_id):
        return await self.db.failed_tasks.delete_one({
            "id": task_id
        })
    

    async def update_task_host(self, task_id, host):
        return await self.db.tasks.update_one({ '_id': ObjectId(task_id) }, { "$set": { "host": host, 'updated_at': datetime.now() } })

    async def update_task_deadline(self, task_id, deadline):
        return await self.db.tasks.update_one({ '_id': ObjectId(task_id) }, { "$set": { "deadline": deadline, 'updated_at': datetime.now() } })

    async def update_task_state(self, task_id, state):
        return await self.db.tasks.update_one({ '_id': ObjectId(task_id) }, { "$set": { "state": state, 'updated_at': datetime.now() } })

    async def update_task_data(self, task_id, data):
        return await self.db.tasks.update_one({ '_id': ObjectId(task_id) }, { "$set": { "data": data, 'updated_at': datetime.now() } })

    async def update_task_result(self, task_id, result, status):
        return await self.db.tasks.update_one({ '_id': ObjectId(task_id) }, { "$set": { "status": status, 'result': result, 'updated_at': datetime.now() } })

    async def get_task(self, task_id):
        return await self.db.tasks.find_one({ '_id': ObjectId(task_id) })

    async def get_tasks(self, search={}):
        return await self.db.tasks.find(search).to_list(None)

    async def create_task(self, task):
        return await self.db.tasks.insert_one(task)
    
    async def count_tasks(self, search):
        return await self.db.tasks.count_documents(search)

    
    async def get_cctools_profile(self, profile_name):
        return await self.db.cctools.find_one({ "profile": profile_name })

    async def get_random_cctools_profile(self, id):
        return await self.db.cctools.find_one({ "id": id })

    async def add_cctools_profile(self, data):
        return await self.db.cctools.insert_one(data)

    async def remove_cctools_profile(self, data):
        return await self.db.cctools.delete_one(data)

    async def update_cctools_profile(self, search, data):
        return await self.db.cctools.update_one(search, { "$set": data })

    
    async def get_dive_profile(self, profile_name):
        return await self.db.dive.find_one({ "profile": profile_name })

    async def put_dive_profile(self, data):
        return await self.db.dive.update_one({ "profile": data["profile"] }, { "$set": data }, upsert=True)

    async def remove_dive_profile(self, data):
        return await self.db.dive.delete_one(data)



    async def get_weight_ordered_accounts(self, user_id, pass_accounts = None, include_all_no_ap_accounts = False):
        db_config = await self.get_config()

        finish_levels_conditions = list(map(lambda data: { "$and": [ { "$lt": [ "$stat.level", data[2] ] }, { "$gte": [ "$stat.points", data[0] ] }, { "$lt": [ "$stat.points", data[1] ] } ] }, db_config["finish_level_ranges"]))

        return await self.db.accounts.aggregate([
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            { "$eq": [ "$active", True ] },
                            { "$ne": [ "$stat.banned", True ] },
                            { "$not": { "$gt": [ "$stat.points", db_config["max_points_limit"] ] } },
                            { "$eq": [ "$stat.hasAlphaPass", pass_accounts ] } if pass_accounts is not None else True
                        ]
                    }
                }
            },
            { "$lookup": {
                "from": "chest_sessions",
                "let": { "account_id": "$_id" },
                "pipeline": [
                    { "$match": { "$expr": { 
                        "$and": [
                            { "$eq": [ "$account_id", "$$account_id" ] },
                            { "$in": [ "$status", ["new", "repeat"] ] },
                            { "$lt": [ "$available_at", datetime.now() ] }
                        ]
                    } } },
                    { "$project": { "_id": 0, "account_id": 0, "user_id": 0 } }
                ],
                "as": "chest_sessions"
            } },
            {
                "$match": {
                    "$expr": {
                        "$or": [
                            { "$lt": [ "$stat.level", { "$cond": [ "$stat.hasAlphaPass", db_config["max_level_required_ap"], db_config["max_level_required_ap" if include_all_no_ap_accounts else "max_level_required"] ] }  ] },
                            { "$gt": [ { "$size": "$chest_sessions" }, 0 ] },
                            { "$and": [ { "$eq": ["$stat.hasAlphaPass", True ] }, { "$or": finish_levels_conditions } ] }
                        ]
                    }
                }
            },
            { "$lookup": {
                "from": "gamer_activities",
                "let": { "account_id": "$_id" },
                "pipeline": [
                    { "$match": { "$expr": {
                        "$and": [
                            { "$eq": [ "$account_id", "$$account_id" ] },
                            { "$in": [ "$status", ["new", "playing", "post_processing", "post_processing_repeating", "get_jwt_error" ] ] }
                        ]
                    } } }
                ],
                "as": "busy_sessions"
            } },
            {
                "$match": {
                    "$expr": {
                        "$eq": [ { "$size": "$busy_sessions" }, 0 ]
                    }
                }
            },
            { "$unset": "chest_sessions" },
            { "$unset": "busy_sessions" },
            { "$lookup": {
                "from": "account_weights",
                "let": { "account_id": "$_id" },
                "pipeline": [
                    { "$match": { "$expr": { 
                        "$and": [
                            { "$eq": [ "$account_id", "$$account_id" ] },
                            { "$cond": [ { "$eq": [ "$user_id", user_id ] }, True, { "$gte": [ "$weight", 0 ] } ] }
                        ]
                    } } },
                    { "$group": {
                        "_id": "$account_id",
                        "weight": { "$accumulator": {
                            "init": "function() { return 0 }",
                            "accumulate": f"function (accWeight, db_user_id, weight) {{ return db_user_id == {user_id} ? accWeight + weight : accWeight - (weight / 2)}}",
                            "accumulateArgs": ["$user_id", "$weight"],
                            "merge": "function (weight1, weight2) { return weight1 + weight2 }",
                            "lang": "js"
                        } }
                    } },
                    { "$project": { "_id": 0, "account_id": 0, "user_id": 0 } }
                ],
                "as": "weight"
            } },
            { "$addFields": { "weight": { "$first": "$weight" } } },
            { "$addFields": { "weight": { "$ifNull": [ "$weight.weight", 0 ] } } },
            # {
            #     "$match": {
            #         "$expr": {
            #             "$gte": [ "$weight", 0 ]
            #         }
            #     }
            # },
            { "$sort": { "weight": DESCENDING } },
            { "$unset": "weight" }
        ]).to_list(None)
    
    async def get_top_account_weight(self, account_id):
        return await self.db.account_weights.find_one({ "account_id": account_id }, sort=[( 'weight', DESCENDING )])

    async def apply_gamer_account_weight(self, user_id, account_id):
        db_config = await self.get_config()
        top_weight = await self.get_top_account_weight(account_id)
        
        migration_weight = (top_weight["weight"] / 2) if top_weight and top_weight["user_id"] != user_id and top_weight["weight"] > 0 else 0
        weight = db_config["success_weight_points"] + migration_weight
            
        return await self.change_gamer_account_weight(user_id, account_id, weight)

    async def cancel_gamer_account_weight(self, user_id, account_id):
        db_config = await self.get_config()
        return await self.change_gamer_account_weight(user_id, account_id, -db_config["penalty_weight_points"])

    async def change_gamer_account_weight(self, user_id, account_id, weight):
        search = { "user_id": user_id, "account_id": account_id }
        return await self.db.account_weights.update_one(search, { "$set": search, "$inc": { "weight": weight } }, upsert=True)


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

