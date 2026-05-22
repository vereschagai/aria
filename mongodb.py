from pymongo import DESCENDING, ASCENDING
import motor.motor_asyncio


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


    async def is_gamer(self, search):
        return await self.db.gamers.find_one(search) != None

    async def count_gamers(self, search):
        return await self.db.gamers.count_documents(search)

    async def get_gamers(self, search, sort=None):
        return await self.db.gamers.find(search, sort=sort).to_list(None)

    async def get_gamer(self, user_id):
        return await self.db.gamers.find_one({ "id": user_id })

    async def add_gamer(self, id, username, referral, address = None):
        return await self.db.gamers.insert_one({ "id": id, "username": username, "referral": referral, "address": address })

    async def update_gamer(self, search, gamer):
        if "id" in gamer and "username" in search:
            await self.db.gamers.update_many({ "referral_name": search["username"] }, { "$set": { "referral": gamer["id"] }, "$unset": { "referral_name": "" } })

        return await self.db.gamers.update_one(search, { "$set": gamer })

    async def update_gamer_address(self, user_id, address):
        return await self.db.gamers.update_one({ "id": user_id }, { "$set": { "address": address } })


    async def get_accounts(self, search = {}, sort = None):
        return await self.db.accounts.find(search, sort=sort).to_list(None)

    async def put_account(self, profile, data, upsert = True):
        return await self.db.accounts.update_one({ "profile": profile }, { "$set": data }, upsert=upsert)


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


    async def ensure_indexes(self):
        # Role resolution — checked on every incoming message
        await self.db.admin.create_index([("id", ASCENDING), ("superadmin", ASCENDING)])
        await self.db.operators.create_index("id", unique=True)

        # Gamers — high-frequency lookups and referral counts
        await self.db.gamers.create_index("id", unique=True)
        await self.db.gamers.create_index("username", sparse=True)
        await self.db.gamers.create_index("referral")

        # Accounts — profile upserts (sheet sync), gamer page, leaderboard sort
        await self.db.accounts.create_index("profile", unique=True)
        await self.db.accounts.create_index("gamer")
        await self.db.accounts.create_index([("points.points", DESCENDING)])

        # Messages — read/written on every user interaction
        await self.db.messages.create_index("id", unique=True)
