import random
from mongodb import MongoDb
from bson.objectid import ObjectId

db = MongoDb('localhost', 27017, 'aria', None, None)
# db = MongoDb('95.111.241.149', 27017, 'aria', 'telegram_admin', 'VaginaPingvina1996')
# db = MongoDb('95.111.241.149', 27017, 'sandbox_studio_qa', 'telegram_admin', 'VaginaPingvina1996')


async def calculate_rewards(amount):
    username_addresses = {}
    gamers = await db.db.gamers.find({}).to_list(None)
    for gamer in gamers:
        username_addresses[gamer['username']] = gamer['address']

    destribution = {}
    gamer_points = {}
    accounts = await db.db.accounts.find({ "points.points": { "$gt": 0 } }).to_list(None)
    for account in accounts:
        if account['gamer'] not in gamer_points:
            gamer_points[account['gamer']] = 0
        # gamer_points[account['gamer']] += account['points']['points'] + account['tower']['points'] * 7
        gamer_points[account['gamer']] += account['tower']['points']
    
    total_points = sum(gamer_points.values())
    for gamer, points in gamer_points.items():
        address = username_addresses.get(gamer)
        if address not in destribution:
            destribution[address] = 0

        if address is None and points > 0:
            print(f'No address for gamer {gamer}')

        destribution[address] += amount * (points / total_points)

    count = 0
    total = 0
    for address in destribution:
        # print(address)
        # print(f'{address},{round(destribution[address], 6)}')
        print(f'{address},{destribution[address]}')
        total += destribution[address]
        count += 1

    print(count, total)

loop = db.connection.get_io_loop()
loop.run_until_complete(calculate_rewards((57906 - (100 / 0.072) ) * 0.4))  # 40% for gamers