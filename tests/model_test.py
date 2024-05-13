from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    LargeBinary,
)
from sqlalchemy.orm import sessionmaker, declarative_base


engine = create_engine("sqlite:///./test.db")

Base = declarative_base()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Test user table

class User(Base):
    """
    User model.

    Represents a user in the test database.
    """

    __tablename__ = "user_test"
    id = Column(Integer, primary_key=True)
    name = Column(String(30))
    surname = Column(String(30))
    email = Column(String(40))
    password = Column(String(30))
    avatar = Column(LargeBinary())
    created_at = Column(DateTime)


Base.metadata.create_all(engine)
