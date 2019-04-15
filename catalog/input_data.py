from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Icecream, Base, Company, User

engine = create_engine('sqlite:///icecream.db')
# Bind the engine to the metadata of the Base class so that the
# declaratives can be accessed through a DBSession instance
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
# A DBSession() instance establishes all conversations with the database
# and represents a "staging zone" for all the objects loaded into the
# database session object. Any change made against the objects in the
# session won't be persisted into the database until you call
# session.commit(). If you're not happy about the changes, you can
# revert all of them back to the last commit by calling
# session.rollback()
session = DBSession()

# Create dummy user
User1 = User(
    name="priyaranjan reddy", email="priyaranjanreddy.g@gmail.com", picture='')
session.add(User1)
session.commit()


# Company 1
company1 = Company(name="Baskins Robins", user_id=1)
session.add(company1)
session.commit()


icecream1 = Icecream(
    user_id=1,
    name="Bavarian chocolate",
    description="qwerty",
    price='10',
    company=company1)
session.add(icecream1)
session.commit()


print "added menu items!"
