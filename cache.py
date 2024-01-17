from cachetools import TTLCache
import sqlalchemy

from database import User


class Cache:
    def __init__(self, engine):
        # Create a cache with a time-to-live (TTL) of 60 seconds (1 minute)
        self.engine = engine
        self.user_cache = TTLCache(maxsize=100, ttl=60)
        # self.session = sqlalchemy.orm.sessionmaker(bind=self.engine)()

    # Function to retrieve a user from the cache or from the database if not present
    def get_user(self, user_id):
        # Try to get the user from the cache
        user = self.user_cache.get(user_id)

        if user is not None:
            return user

        # If the user is not in the cache, retrieve it from the database
        session = sqlalchemy.orm.sessionmaker(bind=self.engine)()
        user = session.query(User).filter_by(user_id=user_id).first()

        if user is not None:
            # Add the user to the cache
            user.referred_by
            user.referred_users
            self.user_cache[user_id] = user
        session.close()

        return user

    # Function to update a user in both the database and the cache
    def update_user(self, user_id, updated_data):
        # Update the user in the database (replace with your actual database update logic)
        session = sqlalchemy.orm.sessionmaker(bind=self.engine)()
        session.query(User).filter_by(user_id=user_id).update(updated_data)
        session.commit()

        # Update the user in the cache if it exists
        if user_id in self.user_cache:
            user = session.query(User).filter_by(user_id=user_id).first()
            user.referred_by
            user.referred_users
            self.user_cache[user_id] = user

        session.close()


# if __name__ == '__main__':
#     from main import engine
#
#     cache = Cache(engine)
#     user = cache.get_user(596604100)
#     print(user)
#     print(user.referral_link)
#     print(user.referred_by)
#     print(user.referred_users)
#     print(user.joined)
#
#     user = cache.get_user(6895974039)
#     print(user)
#     print(user.referral_link)
#     print(user.referred_by)
#     print(user.referred_users)
#     print(user.joined)
