"""
Season 3 One-Time Migration Script
====================================
Run this ONCE against the production MongoDB via SSH tunnel before deploying the updated bot.

Usage:
    # 1. Open SSH tunnel on your local machine:
    #    ssh -L 27017:127.0.0.1:27017 -p 2223 root@176.29.100.183
    #
    # 2. Run this script:
    #    python3 migration_season3.py

What it does:
    - Adds gamer_id (ObjectId) to every account by looking up gamers.username
    - Freezes current tower.points as season3_start_points
    - Initialises ownership_history, progress_history, and all Season 3 status fields
    - Seeds new config fields (min_progress_points, max_accounts_per_gamer, etc.)
    - Creates new indexes for Season 3 queries

Safe to re-run: uses $setOnInsert-equivalent logic to avoid overwriting existing values.
"""

import asyncio
from datetime import datetime

from mongodb import MongoDb
from config import config as default_config


# Connect to production via SSH tunnel (tunnel maps localhost:27017 → server:27017)
DB_HOST = "localhost"
DB_PORT = 27017
DB_NAME = "aria"
DB_USERNAME = None
DB_PASSWORD = None

db = MongoDb(DB_HOST, DB_PORT, DB_NAME, DB_USERNAME, DB_PASSWORD)


async def migrate():
    print("=" * 60)
    print("Season 3 Migration — starting")
    print("=" * 60)

    # -------------------------------------------------------------------------
    # 1. Ensure all indexes (including new Season 3 indexes)
    # -------------------------------------------------------------------------
    print("\n[1/4] Creating indexes...")
    await db.ensure_indexes()
    print("      Done.")

    # -------------------------------------------------------------------------
    # 2. Build username → gamer document map
    # -------------------------------------------------------------------------
    print("\n[2/4] Loading gamers...")
    gamers = await db.db.gamers.find({}).to_list(None)
    gamer_by_username = { g["username"]: g for g in gamers if "username" in g }
    print(f"      Found {len(gamers)} gamers.")

    # -------------------------------------------------------------------------
    # 3. Migrate accounts
    # -------------------------------------------------------------------------
    print("\n[3/4] Migrating accounts...")
    accounts = await db.get_accounts()
    now = datetime.utcnow()
    migrated = 0
    skipped = 0
    unresolved = []

    for account in accounts:
        profile = account["profile"]

        # Skip if already migrated (season3_start_points already set)
        if "season3_start_points" in account:
            skipped += 1
            continue

        gamer_username = account.get("gamer")
        gamer_doc = gamer_by_username.get(gamer_username) if gamer_username else None
        gamer_id = gamer_doc["_id"] if gamer_doc else None

        if gamer_username and not gamer_doc:
            unresolved.append((profile, gamer_username))

        tower_start = account.get("tower", {}).get("points", 0)

        ownership_entry = {
            "gamer_id": gamer_id,
            "gamer_username": gamer_username,
            "assigned_at": now,
            "released_at": None
        } if gamer_id else None

        update = {
            "gamer_id": gamer_id,
            "season3_start_points": tower_start,
            "ownership_history": [ownership_entry] if ownership_entry else [],
            "progress_history": [],
            "last_progress_at": None,
            "last_synced_at": None,
            "last_notified_day": None,
            "status": "active",
            "available_for_pickup": False,
            "escalated_at": None,
            "pending_proof": None,
        }

        await db.db.accounts.update_one({ "profile": profile }, { "$set": update })
        migrated += 1
        print(f"      ✓ {profile:40s}  gamer_id={'None' if not gamer_id else str(gamer_id)[:8]+'...'} | start_points={tower_start}")

    print(f"\n      Migrated: {migrated}  |  Skipped (already done): {skipped}")

    if unresolved:
        print(f"\n      ⚠️  Could not resolve gamer for {len(unresolved)} accounts:")
        for profile, username in unresolved:
            print(f"         - {profile} → '{username}' not found in gamers collection")

    # -------------------------------------------------------------------------
    # 4. Seed new config fields
    # -------------------------------------------------------------------------
    print("\n[4/4] Seeding config fields...")
    season3_config_fields = [
        "min_progress_points",
        "max_accounts_per_gamer",
        "inactivity_escalation_days",
        "inactivity_day_buffer_hours",
    ]
    existing_config = await db.get_config()
    for field in season3_config_fields:
        if not existing_config or field not in existing_config:
            value = default_config[field]
            await db.update_config(field, value)
            print(f"      + {field} = {value}")
        else:
            print(f"      ~ {field} already set ({existing_config[field]}), skipping")

    # -------------------------------------------------------------------------
    # Done
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Migration complete. Review any ⚠️  warnings above.")
    print("You can now deploy the updated bot.")
    print("=" * 60)


if __name__ == "__main__":
    loop = db.connection.get_io_loop()
    loop.run_until_complete(migrate())
