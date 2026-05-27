from aiogram.types import ReplyKeyboardMarkup

import buttons

superadmin_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
superadmin_start.add(buttons.superadmin_add_admin, buttons.superadmin_remove_admin)
superadmin_start.add(buttons.admin_add_support, buttons.admin_remove_support)
superadmin_start.add(buttons.leaderboard)
superadmin_start.add(buttons.admin_grab_accounts)
superadmin_start.add(buttons.configuration, buttons.feed)
superadmin_start.add(buttons.finished_accounts)
superadmin_start.row(buttons.superadmin_invite_link)

start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
start.add(buttons.account, buttons.leaderboard)
start.add(buttons.pickup_account, buttons.release_account)
start.add(buttons.referral)
start.row(buttons.gamer_invite_friend)

confirm = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
confirm.add(buttons.confirm, buttons.cancel)

back = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
back.add(buttons.back)

backaddressadd = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
backaddressadd.add(buttons.back, buttons.add_address)

backaddresschange = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
backaddresschange.add(buttons.back, buttons.change_address)

support_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
support_start.add(buttons.leaderboard)
support_start.add(buttons.finished_accounts)
support_start.row(buttons.support_invite_link)
