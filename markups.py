from aiogram.types import ReplyKeyboardMarkup

import buttons

superadmin_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
superadmin_start.add(buttons.superadmin_add_admin, buttons.superadmin_remove_admin)
superadmin_start.add(buttons.admin_add_operator, buttons.admin_remove_operator)
superadmin_start.add(buttons.admin_add_support, buttons.admin_remove_support)
superadmin_start.add(buttons.leaderboard)
superadmin_start.add(buttons.admin_grab_accounts)
superadmin_start.add(buttons.configuration, buttons.feed)

admin_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
admin_start.add(buttons.admin_add_operator, buttons.admin_remove_operator)
admin_start.add(buttons.admin_add_support, buttons.admin_remove_support)
admin_start.add(buttons.leaderboard)

start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
start.add(buttons.account, buttons.leaderboard)
start.add(buttons.pickup_account, buttons.release_account)
start.add(buttons.referral)

confirm = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
confirm.add(buttons.confirm, buttons.cancel)

back = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
back.add(buttons.back)

backaddressadd = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
backaddressadd.add(buttons.back, buttons.add_address)

backaddresschange = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
backaddresschange.add(buttons.back, buttons.change_address)

operator_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
operator_start.add(buttons.leaderboard)

support_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
support_start.add(buttons.leaderboard)
