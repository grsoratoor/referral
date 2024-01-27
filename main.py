import asyncio
import csv
import datetime
import logging
import os
import random
from functools import wraps
from io import StringIO

import sqlalchemy
import sqlalchemy.ext.declarative as sed
import telegram
from captcha.image import ImageCaptcha
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
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
import payments.wallet
from cache import Cache
from payments.solana import SolanaWallet
from utils import AdminCommands, Vars

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)

# Define states for the conversation
COLLECTING_WALLET, LEADER_BOARD, VERIFY_SUM, BROADCAST = range(4)

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

# create cache class for users
cache = Cache(engine)
variables = Vars()
admin_commands = AdminCommands()
solana_wallet = SolanaWallet(payments.solana.ENDPOINT)


def create_start_menu():
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
            InlineKeyboardButton(loc.get("menu_withdraw"), callback_data="withdraw")
        ]
    ]

    if user_cfg['Telegram']['ads_contact']:
        user_menu_kb.append([InlineKeyboardButton(variables.ad_button_name, url=variables.ad_button_url)])

    return InlineKeyboardMarkup(user_menu_kb)


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

    await update.message.reply_text(loc.get('conversation_after_start'), reply_markup=ReplyKeyboardRemove())

    if user.referred_by_id and not user.joined:
        # if user already member, don't ask him to join
        if not await is_user_member(context.bot, user_cfg['Telegram']['group_id'], user.user_id):
            await update.message.reply_text(text=f"You are referred to join this chat {user.referred_by.referral_link}")
            return

    await update.message.reply_text(text=loc.get("conversation_open_user_menu"),
                                    reply_markup=create_start_menu(),
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
               f"<i>You will get {variables.reward_amount} {user_cfg['Payments']['currency_symbol']} " \
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
        text = f"Contact {user_cfg['Telegram']['help_username']} for any help/issue related to bot"
    elif query.data == 'developer':
        notification = "Getting developer details"
        text = f"Bot developed by @hackspider"
    elif query.data == 'withdraw':
        await withdraw(update, context)
        return
    else:
        return await leader_board(update, context)

    await query.answer(notification, show_alert=show_alert)
    await query.message.reply_text(text=text, reply_markup=create_start_menu(), parse_mode='HTML')
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
        await query.message.reply_text(text=text, reply_markup=create_start_menu(), parse_mode='HTML')
        await query.delete_message()
        return ConversationHandler.END
    else:
        return ConversationHandler.END

    top_referrals = get_top_referrals(period, limit)
    text = f"<b>{loc.get(f'lb_menu_{query.data}')}</b>\n\n"
    for i, referral in enumerate(top_referrals):
        user = cache.get_user(referral[0])
        text += f"<code>{i + 1}. {user.full_name:<15} - {referral.referral_count:2}</code>\n"

    await query.answer()
    await query.message.reply_text(text=text, reply_markup=leaderboard_rm, parse_mode='HTML')
    await query.delete_message()


async def leader_board_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = {
        'daily': get_top_referrals('daily', 5),
        'weekly': get_top_referrals('weekly', 5),
        'top20': get_top_referrals('all', 20)
    }
    text = f"{loc.get('text_leaderboard')}\n\n"
    for key, top in top_users.items():
        text += f"<b>{loc.get(f'lb_menu_{key}')}</b>\n\n"
        for i, referral in enumerate(top):
            user = cache.get_user(referral[0])
            text += f"<code>{i + 1}. {user.full_name[:30]:<15} - {referral.referral_count:>2}</code>\n"
        text += "\n\n"

    reply_markup = None
    if user_cfg['Telegram']['ads_contact']:
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(variables.ad_button_name, url=variables.ad_button_url)]]
        )
    await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode='HTML')


async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = cache.get_user(update.effective_user.id)
    query = update.callback_query

    if not variables.withdraw_enabled:
        await query.answer(f"Currently withdraw option is disabled.", True)
        return

    if not solana_wallet.is_valid_address(user.wallet):
        await query.answer("Your wallet address is not valid.", True)
        return

    if user.referrals < variables.min_referral:
        await query.answer(f"You need to refer at least {variables.min_referral} to eligible for withdraw.", True)
        return

    if user.balance < variables.min_reward_amount:
        await query.answer(f"You need to have at least {variables.min_reward_amount} amount to withdraw.", True)
        return

    if user.balance == 0:
        await query.answer(f"Your balance is 0.", True)
        return

    try:
        solana_wallet.set_private_key(variables.private_key)
        balance = user.balance
        currency_symbol = user_cfg['Payments']['currency_symbol']
        tx_url = solana_wallet.send(user.wallet, balance)
        cache.update_user(user.user_id, {"claimed": user.reward})
        await query.message.reply_text(f"Rewards of <b>{user.balance} {currency_symbol}</b> sent successfully.",
                                       parse_mode='HTML')
        await query.message.reply_text(tx_url)
        await context.bot.send_message(chat_id=user_cfg['Telegram']['group_id'],
                                       text=loc.get('text_withdraw_proof',
                                                    username=user.mention(),
                                                    balance=balance,
                                                    currency_symbol=currency_symbol,
                                                    tx_url=tx_url),
                                       parse_mode='HTML',
                                       )
    except payments.wallet.PrivateKeyNoneError:
        await query.answer("Admin has not yet configured the wallet to send rewards.", True)
    except payments.wallet.InvalidAddressError:
        await query.answer("Your wallet address is not valid.", True)
    except payments.wallet.NotEnoughBalanceError:
        await query.answer("Admin wallet doesnt have enough balance to pay.", True)


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
    text = f"<b>Admin Help Menu</b>\n\n" \
           f"{admin_commands}\n\n" \
           f"/broadcast - Broadcast message to users\n\n" \
           f"/download - Download all user data\n\n" \
           f"<b>Current Configuration</b>\n\n" \
           f"{variables}"
    await update.message.reply_text(text, parse_mode='HTML')


@admin_only
async def admin_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text.split(' ')
    # Check if the input has the correct format
    if len(input_text) == 1:
        command = admin_commands.get(input_text[0])
        value = None
        text = "Changes applied."
    elif len(input_text) == 2:
        command = admin_commands.get(input_text[0])
        value = input_text[1]
        text = f"Changes applied,\nUpdated the value to {value}"
    else:
        await update.message.reply_text("Invalid command format\nPress /admin to know more.")
        return

    if command.type is not None and value is None:
        await update.message.reply_text("Invalid command format\nCommand needs a value\nPress /admin to know more.")
        return

    # convert value to its type
    try:
        if value:
            value = command.type(value)
    except ValueError:
        await update.message.reply_text("Invalid value. Please provide a valid value.")
        return

    variables.update(command.command, value)

    await update.message.reply_text(text)


# Admin command to set claimed amount equal to reward amount for all users
@admin_only
async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # delete loading message
    await message.delete()
    # Send the original CSV file to the user as a document
    await update.message.reply_document(
        document=csv_output,
        filename="user_data.csv",
        caption="User data."
    )


@admin_only
async def ask_broadcast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send a message you want to broadcast\n"
                                    "Press /cancel to cancel.")
    return BROADCAST


async def send_broadcast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Broadcast started")
    session = sqlalchemy.orm.sessionmaker(engine)()
    users = session.query(db.User).all()
    session.close()

    for user in users:
        try:
            await update.message.copy(chat_id=user.user_id)
        except telegram.error.BadRequest as e:
            logger.error(e)

        await asyncio.sleep(0.1)

    await update.message.reply_text("Broadcast completed!")


@admin_only
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.application.create_task(send_broadcast_msg(update, context), update)


# Function to start the verification process
async def start_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Generate two random values for the sum verification

    image = ImageCaptcha()

    correct_value = random.randint(1000, 9999)
    correct_value = str(correct_value)

    data = image.generate(correct_value)

    # Save the correct sum in the context
    context.user_data['correct_value'] = correct_value

    # Send a message to the user with the values and answer options
    await update.message.reply_photo(data, "send the number you see in image", reply_markup=ReplyKeyboardRemove())

    # Move to the VERIFY_SUM state
    return VERIFY_SUM


# Function to handle user's response to verify the sum
async def verify_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Get the user's response
    user_response = update.message.text

    # Get the correct sum from the context
    correct_value = context.user_data['correct_value']

    # Check if the user's sum matches the correct sum
    if user_response == correct_value:
        cache.update_user(update.effective_user.id, {'verified': True})
        await update.message.reply_text("Congratulations! You've verified you are human!.\n"
                                        "Press /start to start using the bot.")
    else:
        await update.message.reply_text("Oops! The value is incorrect. Please try again.")
        return await start_verification(update, context)

    # End the conversation
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    query = update.callback_query
    notification = "Cancelling operation"
    text = loc.get("conversation_open_user_menu")
    await query.answer(notification)
    await query.message.reply_text(text=text, reply_markup=create_start_menu(), parse_mode='HTML')
    await query.delete_message()

    return ConversationHandler.END


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pass


async def chat_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chat join requests"""
    user = cache.get_user(update.chat_join_request.user_chat_id)

    if not user.verified:
        await update.chat_join_request.decline()
        await context.bot.send_message(chat_id=user.user_id, text="You need to verify you are human before joining.")
        return
    else:
        await update.chat_join_request.approve()

    # prevent getting duplicate joins
    if user.joined:
        return

    cache.update_user(user.user_id, {'joined': True})

    if user.referred_by:
        session = sqlalchemy.orm.sessionmaker(bind=engine)()
        session.query(db.User).filter_by(user_id=user.referred_by_id).update(
            {'reward': db.User.reward + variables.reward_amount},
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
        .filter(db.User.joined == True, db.User.created_at >= start_date, db.User.referred_by_id.isnot(None))
        .group_by(db.User.referred_by_id)
        .order_by(func.count(db.User.user_id).desc())
        .limit(limit)
        .all()
    )
    session.close()
    return top_referrals


async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = sqlalchemy.orm.sessionmaker(engine)()
    total_users = session.query(db.User).count()
    total_referrals = session.query(func.count(db.User.user_id)).filter(db.User.referred_by_id.isnot(None)).scalar()
    total_joined = session.query(func.count(db.User.user_id)).filter(db.User.referred_by_id.isnot(None)).filter(
        db.User.joined.is_(True)).scalar()
    total_rewards = session.query(func.sum(db.User.reward)).scalar()
    total_claimed = session.query(func.sum(db.User.claimed)).scalar()
    session.close()

    text = loc.get(
        "text_bot_stat",
        total_users=total_users,
        total_referrals=total_referrals,
        total_joined=total_joined,
        total_rewards=round(total_rewards, 2),
        total_claimed=round(total_claimed, 2)
    )
    reply_markup = None
    if user_cfg['Telegram']['ads_contact']:
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(variables.ad_button_name, url=variables.ad_button_url)]]
        )

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all errors within the bot."""
    logger.error(context.error)
    if update.message:
        await update.message.reply_text("An error occurred. Please try again later.")
    elif update.callback_query:
        await update.callback_query.answer("An error occurred. Please try again later.")
    else:
        print(update)


def main() -> None:
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(user_cfg["Telegram"]["token"]).build()

    start_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            VERIFY_SUM: [MessageHandler(filters.TEXT & (~filters.COMMAND), verify_captcha)]
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

    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler('broadcast', ask_broadcast_msg)],
        states={
            BROADCAST: [MessageHandler(~filters.COMMAND, start_broadcast),
                        CommandHandler('cancel', cancel)],
        },
        fallbacks=[],
    )

    application.add_handler(start_handler)
    application.add_handler(menu_handler)
    application.add_handler(broadcast_handler)

    application.add_handler(CommandHandler("leaderboard", leader_board_detail))
    application.add_handler(CommandHandler("stat", get_stats))

    # Admin commands
    application.add_handler(CommandHandler("admin", admin_help))
    application.add_handler(CommandHandler("download", download))

    # Commands to set variables
    application.add_handler(CommandHandler(admin_commands.SET_KEY, admin_set))
    application.add_handler(CommandHandler(admin_commands.SET_REWARD_AMOUNT, admin_set))
    application.add_handler(CommandHandler(admin_commands.SET_MIN_REWARD, admin_set))
    application.add_handler(CommandHandler(admin_commands.SET_MIN_REFERRAL, admin_set))
    application.add_handler(CommandHandler(admin_commands.ENABLE_WITHDRAW, admin_set))
    application.add_handler(CommandHandler(admin_commands.DISABLE_WITHDRAW, admin_set))
    application.add_handler(CommandHandler(admin_commands.SET_AD_NAME, admin_set))
    application.add_handler(CommandHandler(admin_commands.SET_AD_URL, admin_set))

    application.add_handler(ChatJoinRequestHandler(chat_join_request))
    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
