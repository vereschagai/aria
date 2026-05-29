from aiogram.dispatcher.filters.state import State, StatesGroup

class TelegramState(StatesGroup):
    superadmin_start = State()
    superadmin_add_admin = State()
    superadmin_remove_admin = State()
    superadmin_remove_admin_confirm = State()
    superadmin_configuration = State()
    superadmin_edit_configuration = State()
    superadmin_feed = State()

    start = State()
    referral = State()
    account = State()
    address = State()
    change_address = State()

    leaderboard = State()

    support_start = State()
    support_remove = State()
    support_remove_confirm = State()
    admin_add_support = State()
    support_dashboard = State()

    gamer_release_account = State()
