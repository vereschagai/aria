from aiogram.types import ReplyKeyboardMarkup

import buttons

superadmin_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
superadmin_start.add(buttons.superadmin_add_admin, buttons.superadmin_remove_admin)
# superadmin_start.add(buttons.admin_add_payer, buttons.admin_remove_payer)
superadmin_start.add(buttons.admin_add_operator, buttons.admin_remove_operator)
# superadmin_start.add(buttons.referral, buttons.statistic)
# superadmin_start.add(buttons.admin_restart_failed_tasks, buttons.admin_stop_bot)
superadmin_start.add(buttons.leaderboard)
superadmin_start.add(buttons.admin_grab_accounts)
superadmin_start.add(buttons.configuration, buttons.feed)
# superadmin_start.add(buttons.refresh_accounts)

admin_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
admin_start.add(buttons.admin_add_payer, buttons.admin_remove_payer)
admin_start.add(buttons.admin_add_operator, buttons.admin_remove_operator)
admin_start.add(buttons.referral, buttons.statistic)
# admin_start.add(buttons.refresh_accounts)
# superadmin_start.add(buttons.admin_add_validator, buttons.admin_remove_validator)

start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
# start.add(buttons.play, buttons.software)
start.add(buttons.account, buttons.leaderboard)

balance = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
balance.add(buttons.back, buttons.withdrawal)

withdrawal = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
withdrawal.add(buttons.back, buttons.withdraw_all)

confirm = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
confirm.add(buttons.confirm, buttons.cancel)

payer_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
payer_start.add(buttons.payer_withdraw_list)

payer_process = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
payer_process.add(buttons.back, buttons.payer_done)

back = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
back.add(buttons.back)

terms = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
terms.add(buttons.accept, buttons.decline)

yesno = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
yesno.add(buttons.yes, buttons.no)

lets_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
lets_start.add(buttons.go)

backdone = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
backdone.add(buttons.back, buttons.done)

backsoftdone = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
backsoftdone.add(buttons.back, buttons.soft_done)

done = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
done.add(buttons.done)

repeat =  ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
repeat.add(buttons.more, buttons.home)

got_it = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
got_it.add(buttons.got_it)

backaddressadd = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
backaddressadd.add(buttons.back, buttons.add_address)

backaddresschange = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
backaddresschange.add(buttons.back, buttons.change_address)

ok_go = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
ok_go.add(buttons.back, buttons.ok_go)

all_fine = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
all_fine.add(buttons.all_fine)

proxy = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
proxy.add(buttons.red_proxy)

closed = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
closed.add(buttons.closed)


operator_start = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
operator_start.add(buttons.challenges)
operator_start.add(buttons.statistic, buttons.leaderboard)
# operator_start.add(buttons.refresh_accounts)

operator_challenges = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
operator_challenges.add(buttons.add_challenge, buttons.edit_challenge)
operator_challenges.add(buttons.enable_challenge, buttons.disable_challenge)
operator_challenges.add(buttons.change_priority_challenge)

edit_challenge = ReplyKeyboardMarkup(resize_keyboard=True, selective=True, one_time_keyboard=False)
edit_challenge.add(buttons.back, buttons.youtube_link)
edit_challenge.add(buttons.time, buttons.points)
edit_challenge.add(buttons.quest_info, buttons.text)
