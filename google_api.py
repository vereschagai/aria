import asyncio
import os

from apiclient import discovery
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload

from tenacity import retry, wait_exponential

class GoogleSheets:
    def __init__(self, aria_gameplay_sheet_id):
        self.loop = asyncio.new_event_loop()

        scopes = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/spreadsheets"]
        secret_file = os.path.join(os.getcwd(), 'client_secret.json')

        self.aria_gameplay_sheet_id = aria_gameplay_sheet_id

        self.accounts_page = "Accounts"

        credentials = service_account.Credentials.from_service_account_file(secret_file, scopes=scopes)
        self.sheets_service = discovery.build('sheets', 'v4', credentials=credentials)
        self.sheets = self.sheets_service.spreadsheets()
        self.drive_service = discovery.build('drive', 'v3', credentials=credentials)

    def __build_accounts_range(self, from_range, to_range):
        return self.__build_range(self.accounts_page, from_range=from_range, to_range=to_range)

    def __build_range(self, sheet_id, from_range, to_range):
        return f'{sheet_id}!{from_range}:{to_range}'

    @retry(wait=wait_exponential(multiplier=1, min=1, max=60))
    def __get_sheet_values(self, spreadsheet_id, range_name):
        result = self.sheets.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        return result.get('values', [])

    @retry(wait=wait_exponential(multiplier=1, min=1, max=60))
    def __update_sheet_values(self, spreadsheet_id, range_name, values):
        self.sheets.values().update(spreadsheetId=spreadsheet_id, body={ 'values': values }, range=range_name, valueInputOption='USER_ENTERED').execute()



    def get_accounts(self):
        return self.__get_sheet_values(self.aria_gameplay_sheet_id, self.__build_accounts_range('A2', 'AAAA'))

    def put_accounts_raw(self, range, data):
        return self.__update_sheet_values(self.aria_gameplay_sheet_id, range, data)

