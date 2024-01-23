import logging
from datetime import datetime

from sqlalchemy import Column, ForeignKey
from sqlalchemy import Integer, BigInteger, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref

log = logging.getLogger(__name__)

# Create a base class to define all the database subclasses
TableDeclarativeBase = declarative_base()


# Define all the database tables using the sqlalchemy declarative base
class User(TableDeclarativeBase):
    """A Telegram user who used the bot at least once."""

    # Telegram data
    user_id = Column(BigInteger, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String)
    username = Column(String)
    language = Column(String, nullable=False)

    # referral data
    referral_link = Column(String)
    referred_by_id = Column(BigInteger, ForeignKey("users.user_id"))
    referred_by = relationship("User", backref=backref("referred_users"), remote_side="User.user_id",
                               primaryjoin="User.referred_by_id == User.user_id")

    # default data
    blocked = Column(Boolean, nullable=False, default=False)
    joined = Column(Boolean, nullable=False, default=False)

    # wallet and reward data
    wallet = Column(String)
    reward = Column(Integer, default=0)
    claimed = Column(Integer, default=0)

    # security data
    verified = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Extra table parameters
    __tablename__ = "users"

    def __init__(self, telegram_user, **kwargs):
        # Initialize the super
        super().__init__(**kwargs)
        # Get the data from telegram
        self.user_id = telegram_user.id
        self.first_name = telegram_user.first_name
        self.last_name = telegram_user.last_name
        self.username = telegram_user.username
        if telegram_user.language_code:
            self.language = telegram_user.language_code
        else:
            self.language = kwargs['language']

    def __str__(self):
        """Describe the user in the best way possible given the available data."""
        if self.username is not None:
            return f"@{self.username}"
        elif self.last_name is not None:
            return f"{self.first_name} {self.last_name}"
        else:
            return self.first_name

    def identifiable_str(self):
        """Describe the user in the best way possible, ensuring a way back to the database record exists."""
        return f"user_{self.user_id} ({str(self)})"

    def mention(self):
        """Mention the user in the best way possible given the available data."""
        if self.username is not None:
            return f"@{self.username}"
        else:
            return f'<a href="tg://user?id={self.user_id}">{self.full_name}</a>'

    @property
    def full_name(self):
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        else:
            return self.first_name

    @property
    def referrals(self):
        joined_referred_users = [u for u in self.referred_users if u.joined]
        return len(joined_referred_users)

    @property
    def balance(self):
        return round(self.reward - self.claimed, 4)

    def __repr__(self):
        return f"<User {self.mention()} referred by {self.referred_by_id}>"


class Admin(TableDeclarativeBase):
    """administrator with his permissions."""

    # The telegram id
    user_id = Column(BigInteger, ForeignKey("users.user_id"), primary_key=True)
    user = relationship("User")
    # Permissions
    block_users = Column(Boolean, default=False)
    is_owner = Column(Boolean, default=False)
    live_mode = Column(Boolean, default=False)

    # Extra table parameters
    __tablename__ = "admins"

    def __repr__(self):
        return f"<Admin {self.user_id}>"
