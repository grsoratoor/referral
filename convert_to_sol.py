import sqlalchemy

import database as db

engine = sqlalchemy.create_engine("sqlite:///database.sqlite")
db.TableDeclarativeBase.metadata.bind = engine

session = sqlalchemy.orm.sessionmaker(bind=engine)()

users = session.query(db.User).all()

for user in users:
    reward = user.reward
    claimed = user.claimed

    print(user.full_name, reward, claimed)
    user.reward = round(reward * 80, 5)
    user.claimed = round(claimed * 80, 5)

session.commit()
session.close()
