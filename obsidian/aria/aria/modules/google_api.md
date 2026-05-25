# Module: google_api.py

**Type:** External API wrapper  
**Lines:** 36  
**Class:** `GoogleSheets`

## Responsibilities

Wraps the Google Sheets API. Provides a single method `get_accounts()` that returns raw row data for the Accounts tab. Called only by [[modules/sheet_synchonizer]].

## Authentication

Service account credentials loaded from `client_secret.json` at runtime (file must exist in working directory — gitignored). Uses `google-api-python-client` + `google-auth`.

⚠️ `client_secret.json` is committed to the repo directory (gitignored but present). Needs BFG/`git filter-branch` to scrub from history.

## `get_accounts() → list`

Returns `Accounts!A2:AQ` sheet values. Decorated with `@retry` (tenacity exponential backoff).

## Known Issues (fixed in code review)

- Dead `self.loop = asyncio.new_event_loop()` — removed. The created loop was never run or closed (resource leak).
- Uses a **synchronous** HTTP client inside async code. Calling `api.get_accounts()` in `sheet_synchonizer.grab_accounts()` blocks the asyncio event loop during the Sheets API round-trip. Not a correctness bug but a latency risk during syncs. Full fix requires running in an executor (`loop.run_in_executor()`).

## Dependencies

- `google-api-python-client==2.2.0`
- `google-auth==1.30.0`
- `tenacity` — retry decorator
- `client_secret.json` — must exist at runtime
