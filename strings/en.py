# Strings / localization file for greed
# Can be edited, but DON'T REMOVE THE REPLACEMENT FIELDS (words surrounded by {curly braces})

# Currency symbol
currency_symbol = "$"

# Conversation: the start command was sent and the bot should welcome the user
conversation_after_start = """Welcome shiller ! 👋

This bot is created by $SHILL 
| Shill To Earn Project On Sol

Join Us For More Info :
🕊️ https://x.com/ShillOnSoL
🌐 https://shillbot.tech/

You can start using this bot to earn $SHILL or $SOL by just referring your friends joining this project telegram group!

Say goodbye to old ways of shillling and start getting proper rewards now!"""

# Conversation: to send an inline keyboard you need to send a message with it
conversation_open_user_menu = "What would you like to do?\n" \
                              "\n" \
                              "<i>Press a key on the bottom keyboard to select an operation.</i>"

# Conversation: like above, but for administrators
conversation_open_admin_menu = "You are a 💼 <b>Manager</b> of this store!\n" \
                               "What would you like to do?\n" \
                               "\n" \
                               "<i>Press a key on the bottom keyboard to select an operation.\n" \
                               "If the keyboard has not opened, you can open it by pressing the button with four small" \
                               " squares in the message bar.</i>"

# User menu: referral link
menu_referral_link = "🔗 Referral link"

# User menu: referral status
menu_referral_status = "👥 My referrals"

# User menu: leaderboard
menu_leaderboard = "🥇 Leaderboard"

# User menu: rewards
menu_rewards = "🏆 Rewards"

# User menu: help
menu_help = "ℹ️ Help"

# User_menu: connect
menu_connect = "💼 Connect"

#User menu: Developer
menu_developer = "👨🏻‍💻 Bot Developed By"

# User_menu: advertise
menu_ads = "🗞 Advertise Your Project Here"

# Admin menu: go to user mode
menu_user_mode = "👤 Switch to customer mode"

# Menu: cancel
menu_cancel = "🔙 Cancel"

# Menu: skip
menu_skip = "⏭ Skip"

# Menu: done
menu_done = "✅️ Done"

# Menu: pay invoice
menu_pay = "💳 Pay"

# Menu: complete
menu_complete = "✅ Complete"

# Menu: refund
menu_refund = "✴️ Refund"

# Menu: stop
menu_stop = "🛑 Stop"

# Menu: help menu
menu_help = "❓ Help / Support"

# Menu: guide
menu_guide = "📖 Guide"

# Menu: next page
menu_next = "▶️ Next"

# Menu: previous page
menu_previous = "◀️ Previous"

# Menu: contact the shopkeeper
menu_contact_admin = "👨‍💼 Contact the admin"

# Menu: generate transactions .csv file
menu_csv = "📄 .csv"

# Menu: edit admins list
menu_edit_admins = "🏵 Edit Managers"

# Menu: language
menu_language = "🇬🇧 Language"

# LeaderBoard Menu: daily
lb_menu_daily = "🏅 Daily Champions"

# LeaderBoard Menu: weekly
lb_menu_weekly = "🧙‍♂️ Weekly Wizards"

# LeaderBoard Menu: daily
lb_menu_top3 = "🤟🏻 Premier Trio"

# LeaderBoard Menu: daily
lb_menu_top5 = "🖐 Superior 5"

# LeaderBoard Menu: daily
lb_menu_top10 = "👐🏻 Prime 10"

# LeaderBoard Menu: daily
lb_menu_top20 = "🦍 Twenty Titans"

# Emoji: unprocessed order
emoji_not_processed = "*️⃣"

# Emoji: completed order
emoji_completed = "✅"

# Emoji: refunded order
emoji_refunded = "✴️"

# Emoji: yes
emoji_yes = "✅"

# Emoji: no
emoji_no = "🚫"

# Info:
bot_info = ""

# Text
text_admin_help = "<b>Admin Commands</b>\n\n" \
                  "/stat \nGet bot stats\n\n" \
                  "/set_reward_amount 0.3 \nsets reward to 0.3 $\n\n" \
                  "/set_claimed yes \nDownloads csv file having payment details and updates the " \
                  "claimed amount for all users"

text_leaderboard = "<b>🏆 Leader Board 🏆</b>"

text_bot_stat = "<b>Bot Stats</b>\n\n<code>" \
                "Total Users     : {total_users}\n" \
                "Total Referrals : {total_referrals}\n" \
                "Total Reward    : {total_rewards}\n" \
                "Total Claimed   : {total_claimed}</code>"

# Help: guide
help_msg = ""

# Help: contact admins
contact_admins = "Currently, the staff available to provide user assistance is composed of:\n" \
                 "{admins}\n" \
                 "<i>Click / Tap one of their names to contact them in a Telegram chat.</i>"

# Error: message received not in a private chat
error_nonprivate_chat = "⚠️ This bot only works in private chats."
