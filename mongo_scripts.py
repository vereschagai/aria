from mongodb import MongoDb

db = MongoDb('localhost', 27017, 'aria', None, None)
# db = MongoDb('176.29.100.183', 27017, 'aria', 'telegram_admin', '<password>')
# db = MongoDb('95.111.241.149', 27017, 'aria_qa', 'telegram_admin', '<password>')


async def calculate_rewards(amount):
    """
    Season 3 reward calculation.

    Score per gamer = Σ positive progress_history.delta across ALL accounts
    (including accounts previously owned, so released accounts still count).
    Distribution is proportional to Season 3 score.
    """
    # Single aggregation — one DB round-trip for all gamers
    season_entries = await db.get_all_gamers_season_points()
    if not season_entries:
        print("No Season 3 points found — nothing to distribute.")
        return

    # Batch-resolve gamer ObjectIds → username + address
    oids = [e["_id"] for e in season_entries if e["_id"] is not None]
    gamers_list = await db.db.gamers.find({"_id": {"$in": oids}}).to_list(None)
    oid_to_gamer = {g["_id"]: g for g in gamers_list}

    gamer_data = {}  # username -> {points, address}
    for entry in season_entries:
        gamer = oid_to_gamer.get(entry["_id"])
        if not gamer or not gamer.get("username"):
            continue
        gamer_data[gamer["username"]] = {
            "points": entry["total"],
            "address": gamer.get("address"),
        }

    if not gamer_data:
        print("No Season 3 points found — nothing to distribute.")
        return

    total_points = sum(v["points"] for v in gamer_data.values())

    distribution = {}  # address -> reward amount
    for username, data in gamer_data.items():
        address = data["address"]
        points = data["points"]

        if address is None:
            print(f"WARNING: no wallet address for @{username} ({points} pts — skipped)")
            continue

        if address not in distribution:
            distribution[address] = 0
        distribution[address] += amount * (points / total_points)

    count = 0
    total = 0.0
    for address, reward in distribution.items():
        print(f"{address},{reward}")
        total += reward
        count += 1

    print(f"\n{count} addresses, {total:.6f} distributed out of {amount}")


if __name__ == "__main__":
    loop = db.connection.get_io_loop()
    loop.run_until_complete(calculate_rewards((57906 - (100 / 0.072)) * 0.4))  # 40% for gamers
