from datetime import datetime

from mongodb import MongoDb
from google_api import GoogleSheets

# Sheet column layout (0-indexed):
#   [0]  Profile
#   [1]  Login
#   [2]  Password
#   [3]  Proxy  (host:port:login:pass, or '#N/A' if unset)
#   [4]  Old Gamer  (Season 1 owner @handle — ignored during sync, used only by migration)
#   [5]  Active  (profile name if active in S3, '#N/A' if not)
#   [6]  Gamer   (current S3 assignment — IGNORED, assignment is DB-only under Option C)
#   [7]  TP Start  (points;rank;floor — Season 1 ending = Season 3 fixed baseline)
#   [8+] Daily sync columns  (points;rank;floor — one column per day, appended by automation)


class GoogleSheetSynchonizer:
    def __init__(self, db: MongoDb, api: GoogleSheets, progress_monitor=None):
        self.db = db
        self.api = api
        self.progress_monitor = progress_monitor  # injected after ProgressMonitor is created

    async def grab_accounts(self):
        sheet_accounts = self.api.get_accounts()

        config = await self.db.get_config()
        min_progress = config.get("min_progress_points", 50) if config else 50

        for sheet_account in sheet_accounts:
            # --- Row-level guards ---
            profile = sheet_account[0].strip() if sheet_account else ""
            if not profile:
                continue

            # Must have at least the Active column (index 5)
            if len(sheet_account) < 6:
                continue

            # Skip accounts not active in Season 3
            if sheet_account[5] == "#N/A":
                continue

            # Skip accounts with no proxy configured
            if sheet_account[3] == "#N/A":
                continue

            account_data = self.__make_db_account(sheet_account)
            existing = await self.db.get_account(profile)
            now = datetime.utcnow()

            if existing is None:
                # Brand-new account — seed progress_history with TP Start (col 7) as baseline.
                start_points = account_data.pop("tp_start")
                seed_entry = {
                    "synced_at": now,
                    "tower_points": start_points,
                    "delta": start_points,
                    "gamer_id": None,
                }
                account_data["gamer_id"] = None
                account_data["ownership_history"] = []
                account_data["progress_history"] = [seed_entry]
                account_data["last_progress_at"] = None
                account_data["last_synced_at"] = now
                account_data["last_notified_day"] = None
                account_data["status"] = "released"
                account_data["escalated_at"] = None
                await self.db.db.accounts.insert_one(account_data)
                continue

            # --- Existing account: compute progress delta ---
            new_tower_points = account_data["tower"]["points"]
            history = existing.get("progress_history", [])

            prev_points = history[-1]["tower_points"] if history else new_tower_points
            delta = new_tower_points - prev_points

            progress_entry = {
                "synced_at": now,
                "tower_points": new_tower_points,
                "delta": delta,
                "gamer_id": existing.get("gamer_id"),  # snapshot who owned at sync time
            }

            # Explicit update — only fields that come from the sheet.
            # gamer_id and ownership are NEVER touched here (Option C: DB-only assignment).
            update_fields = {
                "profile":        account_data["profile"],
                "login":          account_data["login"],
                "password":       account_data["password"],
                "proxy":          account_data["proxy"],
                "tower":          account_data["tower"],
                "last_synced_at": now,
            }

            if delta >= min_progress:
                update_fields["last_progress_at"] = now

            await self.db.db.accounts.update_one(
                {"profile": profile},
                {
                    "$set": update_fields,
                    "$push": {"progress_history": progress_entry},
                }
            )

        # Run inactivity checks after all accounts are updated
        if self.progress_monitor:
            await self.progress_monitor.check_all()

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def __make_db_account(self, account: list) -> dict:
        """
        Parse one sheet row into a dict suitable for MongoDB.
        Returns an extra 'tp_start' key with the Season 3 baseline tower points
        (from col 7 / TP Start). Callers must pop it before inserting into the DB.
        """
        proxy_raw = account[3] if len(account) > 3 else ""
        proxy_data = proxy_raw.split(':') if proxy_raw not in ("", "#N/A") else []

        # TP Start (col 7) — fixed Season 1 ending baseline, never changes after migration
        tp_start_raw = account[7] if len(account) > 7 else ""
        tp_start = self.__parse_tower(tp_start_raw)

        # Current tower points — last daily column (col 8+), appended by automation
        # account[-1] is the rightmost column; guard ensures it's beyond the header cols
        tp_current_raw = account[-1] if len(account) > 8 else ""
        tp_current = self.__parse_tower(tp_current_raw)

        return {
            "profile":  account[0].strip(),
            "login":    account[1] if len(account) > 1 else "",
            "password": account[2] if len(account) > 2 else "",
            "proxy": {
                "host":     proxy_data[0],
                "port":     int(proxy_data[1]),
                "login":    proxy_data[2],
                "password": proxy_data[3],
            } if len(proxy_data) == 4 else {},
            "tower": {
                "points": tp_current["points"],
                "rank":   tp_current["rank"],
                "floor":  tp_current["floor"],
            },
            # Returned separately — used as the seed progress_history entry for new accounts
            "tp_start": tp_start["points"],
        }

    @staticmethod
    def __parse_tower(raw: str) -> dict:
        """
        Parse 'points;rank;floor' string.
        Handles NaN, empty strings, missing values — always returns safe zeros.
        """
        def safe_int(v: str) -> int:
            v = v.strip()
            if v.lower() == "nan" or v == "":
                return 0
            try:
                return int(float(v))
            except (ValueError, TypeError):
                return 0

        parts = raw.split(';') if raw else []
        return {
            "points": safe_int(parts[0]) if len(parts) > 0 else 0,
            "rank":   safe_int(parts[1]) if len(parts) > 1 else 0,
            "floor":  safe_int(parts[2]) if len(parts) > 2 else 0,
        }
