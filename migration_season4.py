"""
Season 4 migration — run once on production before deploying the Season 4 bot.

What it does (per account that has season3_start_points):
  1. Prepends a seed progress_history entry (delta = season3_start_points, gamer_id = null).
  2. Closes any open ownership_history entry (released_at = now).
  3. Strips gamer_username from all ownership_history entries.
  4. Sets status = "released", gamer_id = null.
  5. $unset season3_start_points, available_for_pickup, gamer (S1 legacy), pending_proof, release_request.

Idempotent — accounts without season3_start_points are skipped.

Run via SSH tunnel (localhost:27017 → production):
    python3 migration_season4.py
"""

import asyncio
from datetime import datetime

import motor.motor_asyncio

DB_HOST = "localhost"
DB_PORT = 27017
DB_NAME = "aria"

client = motor.motor_asyncio.AsyncIOMotorClient(f"mongodb://{DB_HOST}:{DB_PORT}")
db = client[DB_NAME]


async def migrate():
    now = datetime.utcnow()

    accounts = await db.accounts.find(
        {"season3_start_points": {"$exists": True}}
    ).to_list(None)

    print(f"Found {len(accounts)} accounts to migrate\n")

    migrated = 0
    failed = 0

    for account in accounts:
        profile = account.get("profile", "?")
        try:
            start_points = account["season3_start_points"]
            existing_history = account.get("progress_history", [])
            ownership_history = account.get("ownership_history", [])

            seed_entry = {
                "synced_at": now,
                "tower_points": start_points,
                "delta": start_points,
                "gamer_id": account.get("gamer_id"),
            }
            new_history = [seed_entry] + existing_history

            # Close the open ownership_history entry and strip gamer_username
            new_ownership = []
            for entry in ownership_history:
                new_entry = {
                    "gamer_id": entry.get("gamer_id"),
                    "assigned_at": entry.get("assigned_at"),
                    "released_at": entry.get("released_at") if entry.get("released_at") is not None else now,
                }
                new_ownership.append(new_entry)

            await db.accounts.update_one(
                {"_id": account["_id"]},
                {
                    "$set": {
                        "status": "released",
                        "gamer_id": None,
                        "progress_history": new_history,
                        "ownership_history": new_ownership,
                        "last_notified_day": None,
                        "escalated_at": None,
                        "last_progress_at": None,
                    },
                    "$unset": {
                        "season3_start_points": "",
                        "available_for_pickup": "",
                        "gamer": "",
                        "pending_proof": "",
                        "release_request": "",
                    },
                }
            )

            migrated += 1
            print(f"  OK  {profile}  (start={start_points}, history_entries={len(existing_history)})")

        except Exception as e:
            failed += 1
            print(f"  ERR {profile}  — {e}")

    print(f"\nDone: {migrated} migrated, {failed} failed")

    remaining = await db.accounts.count_documents({"season3_start_points": {"$exists": True}})
    if remaining == 0:
        print("Verification: OK — no unmigrated accounts remain")
    else:
        print(f"Verification: WARN — {remaining} accounts still have season3_start_points")


if __name__ == "__main__":
    asyncio.run(migrate())
