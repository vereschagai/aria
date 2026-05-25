"""
Combined migration script (Season 3 → Season 4).

Run once on production before deploying the updated bot.

Usage:
    1. Open SSH tunnel: ssh -L 27017:127.0.0.1:27017 -p 2223 root@176.29.100.183
    2. python3 migration.py

Steps:
    Season 3:
    - Ensures all indexes
    - Adds gamer_id to accounts by resolving username from gamers collection
    - Freezes season3_start_points from current tower.points
    - Initialises ownership_history, progress_history, and status fields
    - Seeds new config fields

    Season 4:
    - Seeds progress_history[0] from season3_start_points
    - Closes open ownership_history entries, strips gamer_username
    - Sets status="released", gamer_id=None
    - Unsets obsolete fields (season3_start_points, available_for_pickup, etc.)

Both steps are idempotent — already-migrated accounts are skipped.
"""

import asyncio
import logging
import os
from datetime import datetime

from mongodb import MongoDb
from google_api import GoogleSheets
from config import config as default_config

logging.basicConfig(level=logging.INFO, format="%(message)s")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 27017))
DB_NAME = os.environ.get("DB_NAME", "aria")
DB_USERNAME = os.environ.get("DB_USERNAME")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

ARIA_GAMEPLAY_SHEET_ID = "18NtTSuIWVU9sGdnJ_NGlnsowPD1oBtUyZmCULvmAcZ4"

# Sheet column layout (0-indexed):
#   [0]  Profile (Octo profile name)
#   [1]  Login
#   [2]  Password
#   [3]  Proxy
#   [4]  Seed phrase (MM sid)
#   [5]  Active marker
#   [6]  MM address
#   [12] Wallet password


def load_sheet_data() -> dict:
    """Returns profile -> {login, password, proxy_raw, seed, wallet_password} from Google Sheets."""
    gs = GoogleSheets(aria_gameplay_sheet_id=ARIA_GAMEPLAY_SHEET_ID)
    rows = gs.get_accounts()
    data = {}
    for row in rows:
        if not row:
            continue
        profile = row[0].strip() if row[0] else ""
        if not profile:
            continue
        data[profile] = {
            "login": row[1] if len(row) > 1 else "",
            "password": row[2] if len(row) > 2 else "",
            "proxy_raw": row[3] if len(row) > 3 else "",
            "seed": row[4] if len(row) > 4 else "",
            "address": row[6] if len(row) > 6 else "",
            "wallet_password": row[12] if len(row) > 12 else "",
        }
    return data


async def migrate_season3(db: MongoDb, sheet_data: dict, now: datetime) -> None:
    print("\n" + "=" * 60)
    print("Season 3 Migration")
    print("=" * 60)

    print("\n[S3-1/4] Creating indexes...")
    await db.ensure_indexes()
    print("         Done.")

    print("\n[S3-2/4] Loading gamers...")
    gamers = await db.db.gamers.find({}).to_list(None)
    gamer_by_username = {g["username"]: g for g in gamers if "username" in g}
    print(f"         Found {len(gamers)} gamers.")

    print("\n[S3-3/4] Migrating accounts...")
    accounts = await db.get_accounts()
    migrated = 0
    skipped = 0
    unresolved = []

    for account in accounts:
        profile = account["profile"]

        # Idempotent: skip if already migrated
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
            "released_at": None,
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
        await db.db.accounts.update_one({"profile": profile}, {"$set": update})
        migrated += 1
        sheet_info = sheet_data.get(profile, {})
        seed_preview = sheet_info.get("seed", "")[:8] or "—"
        print(
            f"         ✓ {profile:40s}  "
            f"gamer_id={'None' if not gamer_id else str(gamer_id)[:8]+'...'}  "
            f"start_points={tower_start}  seed={seed_preview}"
        )

    print(f"\n         Migrated: {migrated}  |  Skipped (already done): {skipped}")
    if unresolved:
        print(f"\n         WARNING: Could not resolve gamer for {len(unresolved)} accounts:")
        for profile, username in unresolved:
            print(f"                  - {profile} -> '{username}' not found in gamers collection")

    print("\n[S3-4/4] Seeding config fields...")
    season3_fields = [
        "min_progress_points",
        "max_accounts_per_gamer",
        "inactivity_escalation_days",
        "inactivity_day_buffer_hours",
    ]
    existing_config = await db.get_config()
    for field in season3_fields:
        if not existing_config or field not in existing_config:
            value = default_config[field]
            await db.update_config(field, value)
            print(f"         + {field} = {value}")
        else:
            print(f"         ~ {field} already set ({existing_config[field]}), skipping")


async def migrate_season4(db: MongoDb, sheet_data: dict, now: datetime) -> None:
    print("\n" + "=" * 60)
    print("Season 4 Migration")
    print("=" * 60)

    accounts = await db.db.accounts.find(
        {"season3_start_points": {"$exists": True}}
    ).to_list(None)

    print(f"\nFound {len(accounts)} accounts with season3_start_points to migrate")

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

            # Close open ownership entries, strip gamer_username
            new_ownership = []
            for entry in ownership_history:
                new_ownership.append({
                    "gamer_id": entry.get("gamer_id"),
                    "assigned_at": entry.get("assigned_at"),
                    "released_at": entry.get("released_at") if entry.get("released_at") is not None else now,
                })

            await db.db.accounts.update_one(
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
                },
            )

            migrated += 1
            print(f"  OK   {profile}  (start={start_points}, prior_history_entries={len(existing_history)})")
        except Exception as e:
            failed += 1
            print(f"  ERR  {profile}  — {e}")

    print(f"\nDone: {migrated} migrated, {failed} failed")

    remaining = await db.db.accounts.count_documents({"season3_start_points": {"$exists": True}})
    if remaining == 0:
        print("Verification: OK — no unmigrated accounts remain")
    else:
        print(f"Verification: WARN — {remaining} accounts still have season3_start_points")


async def main():
    print("=" * 60)
    print("Combined Migration (Season 3 + Season 4)")
    print("=" * 60)

    print("\nLoading account data from Google Sheets...")
    try:
        sheet_data = load_sheet_data()
        print(f"  Loaded {len(sheet_data)} accounts from sheet")
    except Exception as e:
        print(f"  WARNING: Could not load sheet data: {e}")
        sheet_data = {}

    db = MongoDb(DB_HOST, DB_PORT, DB_NAME, DB_USERNAME, DB_PASSWORD)
    now = datetime.utcnow()

    await migrate_season3(db, sheet_data, now)
    await migrate_season4(db, sheet_data, now)

    print("\n" + "=" * 60)
    print("All migrations complete. Review any WARN lines above.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
