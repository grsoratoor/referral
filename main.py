import csv
import datetime
import logging
import os
import random
from functools import wraps
from io import StringIO

import sqlalchemy
import sqlalchemy.ext.declarative as sed
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    ChatJoinRequestHandler,
    MessageHandler,
    filters, CallbackQueryHandler,
)

import database as db
import localization
import nuconfig
import utils
from cache import Cache

try:
    import coloredlogs
except ImportError:
    coloredlogs = None

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)

# Define states for the conversation
COLLECTING_WALLET, LEADER_BOARD, VERIFY_SUM = range(3)

"""Run the bot."""
# Start logging setup
logging.root.setLevel("INFO")
logger.debug("Set logging level to INFO while the config is being loaded")

# Ensure the template config file exists
if not os.path.isfile("config/template_config.toml"):
    logger.fatal("config/template_config.toml does not exist!")
    exit(254)

# Check where the config path is located from the CONFIG_PATH environment variable
config_path = os.environ.get("CONFIG_PATH", "config/config.toml")

# If the config file does not exist, clone the template and exit
if not os.path.isfile(config_path):
    logger.debug("config/config.toml does not exist.")

    with open("config/template_config.toml", encoding="utf8") as template_cfg_file, \
            open(config_path, "w", encoding="utf8") as user_cfg_file:
        # Copy the template file to the config file
        user_cfg_file.write(template_cfg_file.read())

    logger.fatal("A config file has been created."
                 " Customize it, then restart greed!")
    exit(1)

# Compare the template config with the user-made one
with open("config/template_config.toml", encoding="utf8") as template_cfg_file, \
        open(config_path, encoding="utf8") as user_cfg_file:
    template_cfg = nuconfig.NuConfig(template_cfg_file)
    user_cfg = nuconfig.NuConfig(user_cfg_file)
    if not template_cfg.cmplog(user_cfg):
        logger.fatal("There were errors while parsing the config file. Please fix them and restart greed!")
        exit(2)
    else:
        logger.debug("Configuration parsed successfully!")

# Finish logging setup
logging.root.setLevel(user_cfg["Logging"]["level"])
# Ignore most python-telegram-bot logs, as they are useless most of the time
logging.getLogger("telegram").setLevel("ERROR")
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
# Find the database URI
# Through environment variables first
if db_engine := os.environ.get("DB_ENGINE"):
    logger.debug("Sqlalchemy engine overridden by the DB_ENGINE env var.")
# Then via the config file
else:
    db_engine = user_cfg["Database"]["engine"]
    logger.debug("Using sqlalchemy engine set in the configuration file.")

# Create the database engine
logger.debug("Creating the sqlalchemy engine...")
engine = sqlalchemy.create_engine(db_engine)
logger.debug("Binding metadata to the engine...")
db.TableDeclarativeBase.metadata.bind = engine
logger.debug("Creating all missing tables...")
db.TableDeclarativeBase.metadata.create_all()
logger.debug("Preparing the tables through deferred reflection...")
sed.DeferredReflection.prepare(engine)

# Finding default language
default_language = user_cfg["Language"]["default_language"]

# Create a new Localization object
loc = localization.Localization(
    language=default_language,
    fallback=user_cfg["Language"]["fallback_language"],
    replacements={
        # "user_string": str(user),
        # "user_mention": user.mention(),
        # "user_full_name": user.full_name,
        # "user_first_name": user.first_name,
        "today": datetime.datetime.now().strftime("%a %d %b %Y"),
    }
)


class Config:
    REWARD_AMOUNT = user_cfg['Payments']['reward']
    ADS_CONTACT_URL = user_cfg['Telegram']['ads_contact']


# create cache class for users
cache = Cache(engine)

user_menu_kb = [
    [
        InlineKeyboardButton(loc.get("menu_referral_link"), callback_data="1"),
        InlineKeyboardButton(loc.get("menu_referral_status"), callback_data="2"),
    ],
    [
        InlineKeyboardButton(loc.get("menu_leaderboard"), callback_data="3"),
        InlineKeyboardButton(loc.get("menu_rewards"), callback_data="4"),
    ],
    [
        InlineKeyboardButton(loc.get("menu_connect"), callback_data="5"),
        InlineKeyboardButton(loc.get("menu_help"), callback_data="6"),
    ],
    [
        InlineKeyboardButton(loc.get('menu_ads'), url=Config.ADS_CONTACT_URL)
    ]
]

user_menu_rm = InlineKeyboardMarkup(user_menu_kb)

cancel_kb = [[
    InlineKeyboardButton(loc.get("menu_cancel"), callback_data="cancel"),
]]

cancel_rm = InlineKeyboardMarkup(cancel_kb)

leaderboard_menu_kb = [
    [
        InlineKeyboardButton(loc.get("lb_menu_daily"), callback_data="daily"),
        InlineKeyboardButton(loc.get("lb_menu_weekly"), callback_data="weekly"),
    ],
    [
        InlineKeyboardButton(loc.get("lb_menu_top3"), callback_data="top3"),
        InlineKeyboardButton(loc.get("lb_menu_top5"), callback_data="top5"),
    ],
    [
        InlineKeyboardButton(loc.get("lb_menu_top10"), callback_data="top10"),
        InlineKeyboardButton(loc.get("lb_menu_top20"), callback_data="top20"),
    ],
    [
        InlineKeyboardButton(loc.get("menu_cancel"), callback_data="cancel")
    ],

]

leaderboard_rm = InlineKeyboardMarkup(leaderboard_menu_kb)


async def private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the update is from a private chat
    if update.callback_query.message.chat.type == 'private':
        return True
    else:
        # Send a notification that the command works only in private mode
        notification = "This button works only in private mode."
        await update.callback_query.answer(notification)
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sends a message with menu inline buttons attached."""
    user = cache.get_user(update.effective_user.id)

    if not user:
        referred_by_id = None
        text = update.message.text
        if len(text.split(' ')) == 2:
            referred_by_id = text.split(' ')[1]
            try:
                referred_by_id = int(referred_by_id)
                # user can not refer himself
                if referred_by_id == update.effective_user.id:
                    referred_by_id = None
            except ValueError:
                logger.debug("Non integer referred_by_id")
                referred_by_id = None

        logger.debug(f"Creating user {update.effective_user.id}")
        session = sqlalchemy.orm.sessionmaker(bind=engine)()
        user = db.User(update.effective_user,
                       referred_by_id=referred_by_id,
                       language=user_cfg["Language"]["default_language"])
        session.add(user)
        session.commit()
        # Query the user from the database to get the refreshed user
        user = session.query(db.User).filter_by(user_id=update.effective_user.id).first()
        session.close()

    if not user.verified:
        return await start_verification(update, context)

    await update.message.reply_text(loc.get('conversation_after_start'))

    if user.referred_by_id and not user.joined:
        # if user already member, don't ask him to join
        if not await is_user_member(context.bot, user_cfg['Telegram']['group_id'], user.user_id):
            await update.message.reply_text(text=f"You are referred to join this chat {user.referred_by.referral_link}")
            return

    await update.message.reply_text(text=loc.get("conversation_open_user_menu"),
                                    reply_markup=user_menu_rm,
                                    parse_mode='HTML')


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    show_alert = False
    user = cache.get_user(update.effective_user.id)

    if not await is_user_member(context.bot, user_cfg['Telegram']['group_id'], user.user_id):
        if user.referred_by:
            invite_link = user.referred_by.referral_link
        else:
            chat_invite_link = await context.bot.create_chat_invite_link(
                chat_id=user_cfg['Telegram']['group_id'],
                name='bot',
                creates_join_request=True)
            invite_link = chat_invite_link.invite_link
        notification = "You need to join the group to access the bot"
        show_alert = True
        text = f"Join this chat to use bot\n\n {invite_link}"

    elif query.data == '1':
        if not await private(update, context):
            return
        notification = "Creating referral link"
        if not user.referral_link:
            logger.debug(f"Creating referral link")
            chat_invite_link = await context.bot.create_chat_invite_link(
                chat_id=user_cfg['Telegram']['group_id'],
                name=user.user_id,
                creates_join_request=True)
            user.referral_link = chat_invite_link.invite_link
            cache.update_user(update.effective_user.id, {'referral_link': user.referral_link})
        me = await context.bot.getMe()
        bot_referral_link = f"https://t.me/{me.username}?start={user.user_id}"
        text = f"Here is your referral link \n\n{bot_referral_link}"

    elif query.data == '2':
        if not await private(update, context):
            return
        notification = "Getting referral status"
        text = f"Total Referrals : {user.referrals}\n"

    elif query.data == '3':
        notification = "Getting leader board"
        text = "Leader Board"
        await query.answer(notification, show_alert=show_alert)
        await query.message.reply_text(text=text, reply_markup=leaderboard_rm, parse_mode='HTML')
        await query.delete_message()
        return
        # return LEADER_BOARD

    elif query.data == '4':
        if not await private(update, context):
            return
        notification = "Getting reward status"
        text = f"Total reward : {user.reward} {user_cfg['Payments']['currency_symbol']}\n" \
               f"Claimed reward: {user.claimed} {user_cfg['Payments']['currency_symbol']}\n" \
               f"Balance reward: {user.balance} {user_cfg['Payments']['currency_symbol']}\n\n" \
               f"<i>You will get {Config.REWARD_AMOUNT} {user_cfg['Payments']['currency_symbol']} " \
               f"for each referral</i>"

    elif query.data == '5':
        if not await private(update, context):
            return
        if user.wallet is not None:
            text = f"Your current wallet address\n\n<code>{user.wallet}</code>\n\n" \
                   f"If you want to replace this send your new wallet address."
        else:
            text = f"Please enter your SOLANA wallet address"
        await query.answer()
        await query.message.reply_text(text=text, reply_markup=cancel_rm, parse_mode='HTML')
        await query.delete_message()
        return COLLECTING_WALLET

    elif query.data == '6':
        notification = "Getting help"
        text = f"Contact @johnywest for any help/issue related to bot"
    elif query.data == 'developer':
        notification = "Getting developer details"
        text = f"Bot developed by @hackspider"
    else:
        return await leader_board(update, context)

    await query.answer(notification, show_alert=show_alert)
    await query.message.reply_text(text=text, reply_markup=user_menu_rm, parse_mode='HTML')
    await query.delete_message()


async def leader_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == 'daily':
        period = 'daily'
        limit = 5
    elif query.data == 'weekly':
        period = 'weekly'
        limit = 5
    elif query.data == 'top3':
        period = 'all'
        limit = 3
    elif query.data == 'top5':
        period = 'all'
        limit = 5
    elif query.data == 'top10':
        period = 'all'
        limit = 10
    elif query.data == 'top20':
        period = 'all'
        limit = 20
    elif query.data == 'cancel':
        notification = "Cancelling operation"
        text = loc.get("conversation_open_user_menu")
        await query.answer(notification)
        await query.message.reply_text(text=text, reply_markup=user_menu_rm, parse_mode='HTML')
        await query.delete_message()
        return ConversationHandler.END
    else:
        return ConversationHandler.END

    top_referrals = get_top_referrals(period, limit)
    text = f"<b>{loc.get(f'lb_menu_{query.data}')}</b>\n\n"
    for i, referral in enumerate(top_referrals):
        user = cache.get_user(referral[0])
        if user:
            text += f"<code>{i + 1}. {user.full_name:<15} - {referral.referral_count:2}</code>\n"

    await query.answer()
    await query.message.reply_text(text=text, reply_markup=leaderboard_rm, parse_mode='HTML')
    await query.delete_message()


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.message.from_user.id

        # Check if the user is an admin
        chat_admins = await context.bot.get_chat_administrators(user_cfg['Telegram']['group_id']) or []
        if any(admin.user.id == user_id for admin in chat_admins):
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text("You are not authorized to use this command.")

    return wrapper


@admin_only
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(loc.get('text_admin_help'), parse_mode='HTML')


@admin_only
async def set_reward_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text.split(' ')

    # Check if the input has the correct format
    if len(input_text) != 2:
        await update.message.reply_text("Invalid format. Please provide as /set_reward_amount amount")
        return

    # Extract the amount from the input
    try:
        new_reward_amount = float(input_text[1])
    except ValueError:
        await update.message.reply_text("Invalid amount. Please provide a valid float amount.")
        return

    # Update the config variable
    Config.REWARD_AMOUNT = new_reward_amount

    await update.message.reply_text(f"Reward amount set to {new_reward_amount}")


@admin_only
async def set_ads_contact_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text.split(' ')

    # Check if the input has the correct format
    if len(input_text) != 2:
        await update.message.reply_text("Invalid format. Please provide as /set_ads_contact_url url")
        return

    # Extract the URL from the input
    new_ads_contact_url = input_text[1]

    # Update the config variable
    Config.ADS_CONTACT_URL = new_ads_contact_url

    await update.message.reply_text(f"Ads contact URL set to {new_ads_contact_url}")


# Admin command to set claimed amount equal to reward amount for all users
@admin_only
async def admin_set_claimed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text.split(' ')

    # Check if the input has the correct format
    if len(input_text) != 2 and input_text[1] != 'yes':
        await update.message.reply_text("Invalid format. Please provide as /set_claimed yes")
        return

    message = await update.message.reply_text("Generating csv file ...")

    # Get users from the database
    session = sqlalchemy.orm.sessionmaker(engine)()
    users = session.query(db.User).all()

    # Create a CSV file in-memory
    csv_output = StringIO()
    csv_writer = csv.writer(csv_output)
    csv_writer.writerow(["User Id", "Name", "Wallet Address", "Reward Amount", "Claimed Amount", "Balance Amount"])

    # Populate the CSV file with user data
    for user in users:
        csv_writer.writerow([user.user_id, user.full_name, user.wallet, user.reward, user.claimed, user.balance])

    csv_output.seek(0)

    # Update claimed amount for all users
    for user in users:
        user.claimed = user.reward

    # Commit changes to the database
    session.commit()

    # delete loading message
    await message.delete()
    # Send the original CSV file to the user as a document
    await update.message.reply_document(
        document=csv_output,
        filename="user_data_before_update.csv",
        caption="User data before updating claimed amounts."
    )

    await update.message.reply_text("Claimed amounts updated for all users.")


# Function to start the verification process
async def start_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Generate two random values for the sum verification
    value_a = random.randint(1, 10)
    value_b = random.randint(1, 10)

    # Calculate the correct sum
    correct_sum = value_a + value_b

    # Save the correct sum in the context
    context.user_data['correct_sum'] = correct_sum

    # Generate four options for the user to select
    options = utils.generate_options(correct_sum)

    # Send a message to the user with the values and answer options
    await update.message.reply_text(
        f"Calculate the sum of {value_a} and {value_b}.",
        reply_markup=ReplyKeyboardMarkup(options, one_time_keyboard=True),
    )

    # Move to the VERIFY_SUM state
    return VERIFY_SUM


# Function to handle user's response to verify the sum
async def verify_sum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Get the user's response
    user_response = update.message.text

    # Check if the user's response is a valid integer
    try:
        user_sum = int(user_response)
    except ValueError:
        await update.message.reply_text("Please enter a valid integer as the sum.")
        return VERIFY_SUM

    # Get the correct sum from the context
    correct_sum = context.user_data['correct_sum']

    # Check if the user's sum matches the correct sum
    if user_sum == correct_sum:
        cache.update_user(update.effective_user.id, {'verified': True})
        await update.message.reply_text("Congratulations! You've verified the sum correctly.\n"
                                        "Press /start to start using the bot.")
    else:
        await update.message.reply_text("Oops! The sum is incorrect. Please try again.")
        return await start_verification(update, context)

    # End the conversation
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    query = update.callback_query
    notification = "Cancelling operation"
    text = loc.get("conversation_open_user_menu")
    await query.answer(notification)
    await query.message.reply_text(text=text, reply_markup=user_menu_rm, parse_mode='HTML')
    await query.delete_message()

    return ConversationHandler.END


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pass


async def chat_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chat join requests"""
    user = cache.get_user(update.chat_join_request.user_chat_id)
    await update.chat_join_request.approve()

    # prevent getting duplicate joins
    if user.joined:
        return

    cache.update_user(user.user_id, {'joined': True})

    if user.referred_by:
        session = sqlalchemy.orm.sessionmaker(bind=engine)()
        session.query(db.User).filter_by(user_id=user.referred_by_id).update(
            {'reward': db.User.reward + Config.REWARD_AMOUNT},
            synchronize_session=False)
        session.commit()
        session.close()

        message = await context.bot.send_message(chat_id=user.user_id,
                                                 text=loc.get("conversation_open_user_menu"),
                                                 reply_markup=user_menu_rm,
                                                 parse_mode='HTML')
        await context.bot.send_message(chat_id=user_cfg['Telegram']['group_id'],
                                       text=f"{user.mention()} was referred by {user.referred_by.mention()}",
                                       parse_mode='HTML')
        try:
            await context.bot.delete_message(user.user_id, message.message_id - 1)
        except:
            pass


async def handle_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cache.update_user(update.effective_user.id, {'wallet': update.message.text})
    await update.message.reply_text("Thank you, Your wallet address saved. This will be used to send rewards.")
    await update.message.reply_text(text=loc.get("conversation_open_user_menu"), reply_markup=user_menu_rm,
                                    parse_mode='HTML')
    return ConversationHandler.END


async def is_user_member(bot, chat_id, user_id):
    try:
        # Get information about the user's membership in the chat
        chat_member = await bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        # Handle exceptions (e.g., user not found, bot not in the group)
        logger.debug(f"Error checking user membership: {e}")
        return False


# Function to get top referrals for a specific period
def get_top_referrals(period: str, limit: int):
    today = datetime.datetime.utcnow()

    if period == 'daily':
        start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'weekly':
        start_date = today - datetime.timedelta(days=today.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'all':
        start_date = datetime.datetime.min
    else:
        raise ValueError("Invalid period. Supported periods: 'daily', 'weekly', 'all'")
    session = sqlalchemy.orm.sessionmaker(engine)()
    top_referrals = (
        session.query(db.User.referred_by_id, func.count(db.User.user_id).label('referral_count'))
        .filter(db.User.joined == True, db.User.created_at >= start_date)
        .group_by(db.User.referred_by_id)
        .order_by(func.count(db.User.user_id).desc())
        .limit(limit)
        .all()
    )
    session.close()
    return top_referrals


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all errors within the bot."""
    logger.error(context.error)
    try:
        await context.bot.send_message(update.message.chat_id, "An error occurred. Please try again later.")
    except:
        pass


async def error_handler_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors that occur within callback queries."""
    logger.error(context.error)
    try:
        await update.callback_query.answer("An error occurred. Please try again later.")
    except:
        pass


def main() -> None:
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(user_cfg["Telegram"]["token"]).build()

    # application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_help))
    application.add_handler(CommandHandler("set_reward_amount", set_reward_amount))
    # application.add_handler(CommandHandler("set_ads_contact_url", set_ads_contact_url))
    application.add_handler(CommandHandler("set_claimed", admin_set_claimed))

    application.add_handler(ChatJoinRequestHandler(chat_join_request))
    application.add_error_handler(error_handler)
    application.add_error_handler(error_handler_callback)

    start_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            VERIFY_SUM: [MessageHandler(filters.TEXT & (~filters.COMMAND), verify_sum)]
        },
        fallbacks=[]
    )

    menu_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button)],
        states={
            COLLECTING_WALLET: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_wallet_address),
                                CallbackQueryHandler(cancel)],
            # LEADER_BOARD: [CallbackQueryHandler(leader_board)]
        },
        fallbacks=[],
    )
    application.add_handler(start_handler)
    application.add_handler(menu_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
