import random


def telegram_html_escape(string: str):
    return string.replace("<", "&lt;") \
        .replace(">", "&gt;") \
        .replace("&", "&amp;") \
        .replace('"', "&quot;")


# Function to generate four options for the user to select
def generate_options(correct_sum):
    # Generate three random incorrect options
    incorrect_options = [correct_sum + random.randint(1, 5) for _ in range(3)]

    # Add the correct sum to the options
    options = [[str(option)] for option in incorrect_options + [correct_sum]]

    # Shuffle the options
    random.shuffle(options)

    return options


class Command:
    def __init__(self, command, description, type):
        self.command = command
        self.description = description
        self.type = type

    def __str__(self):
        val = f"/{self.command} - {self.description}"
        if self.type:
            val += f"\nEx: /{self.command} value"
        return val


class AdminCommands:
    SET_KEY = "set_key"
    SET_REWARD_AMOUNT = 'set_reward_amount'
    ENABLE_WITHDRAW = 'enable_withdraw'
    DISABLE_WITHDRAW = 'disable_withdraw'
    SET_MIN_REFERRAL = 'set_min_referral'
    SET_MIN_REWARD = 'set_min_reward'

    def __init__(self):
        self.commands = [
            Command(AdminCommands.SET_KEY, "Set your solana wallet private KEY", str),
            Command(AdminCommands.SET_REWARD_AMOUNT, "Set reward for each referral", float),
            Command(AdminCommands.ENABLE_WITHDRAW, "Enable withdraw for users", None),
            Command(AdminCommands.DISABLE_WITHDRAW, "Disable withdraw for users", None),
            Command(AdminCommands.SET_MIN_REFERRAL, "Set minimum referrals required for withdraw", int),
            Command(AdminCommands.SET_MIN_REWARD, "Set minimum reward required for withdraw", float)
        ]

    def __str__(self):
        val = ""
        for cmd in self.commands:
            val += f"{cmd}\n\n"
        return val

    def get(self, cmd):
        for command in self.commands:
            if command.command == cmd[1:]:
                return command
        return None


class Vars:
    def __init__(self):
        self.private_key: str = None
        self.reward_amount: float = None
        self.withdraw_enabled: bool = False
        self.min_referral: int = None
        self.min_reward_amount: float = None

    def __str__(self):
        text = ""
        for key, val in vars(self).items():
            text += f"{key}: {val}" '\n'
        return text

    def available(self):
        for key, val in vars(self):
            if val is None:
                return False
        return True

    def update(self, cmd, value):
        if cmd == AdminCommands.SET_KEY:
            self.private_key = value
        elif cmd == AdminCommands.SET_REWARD_AMOUNT:
            self.reward_amount = value
        elif cmd == AdminCommands.ENABLE_WITHDRAW:
            self.withdraw_enabled = True
        elif cmd == AdminCommands.DISABLE_WITHDRAW:
            self.withdraw_enabled = False
        elif cmd == AdminCommands.SET_MIN_REFERRAL:
            self.min_referral = value
        elif cmd == AdminCommands.SET_MIN_REWARD:
            self.min_reward_amount = value
