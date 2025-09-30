from mongodb import MongoDb
from google_api import GoogleSheets

class GoogleSheetSynchonizer:
    def __init__(self, db: MongoDb, api: GoogleSheets):
        self.db = db
        self.api = api

    async def grab_accounts(self):
        sheet_accounts = self.api.get_accounts()

        for sheet_account in sheet_accounts:
            profile = sheet_account[0]

            if profile == "":
                continue
            
            await self.db.put_account(profile, self.__make_db_account(sheet_account))

    def __make_db_account(self, account):
        proxy_data = account[3].split(':')
        points = account[len(account) - 1] if len(account) > 5 else "0"
        
        return {
            "profile": account[0],
            "login": account[1],
            "password": account[2],
            "proxy": {
                "host": proxy_data[0],
                "port": int(proxy_data[1]),
                "login": proxy_data[2],
                "password": proxy_data[3]
            } if len(proxy_data) == 4 else {},
            "gamer": account[4].lstrip("@") if len(account) > 4 and account[4] != "" else None,
            "points": int(points) if points.isdigit() else 0,
        }

