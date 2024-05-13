from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from database import Base, engine


# User table


class User(Base):
    """
    User model.

    Represents a user in the system.
    """

    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(100), nullable=False)
    avatar = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, nullable=False)


# Messages table


class Message(Base):
    """
    Message model.

    Represents a message sent in a chat channel.
    """

    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    content = Column(String(500), nullable=False)
    channel_id = Column(String(100), ForeignKey("channels.channel_id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    channel = relationship("Channel", foreign_keys=[channel_id])
    user = relationship("User", foreign_keys=[user_id])


# Channel table


class Channel(Base):
    """
    Channel model.

    Represents a chat channel between users.
    """

    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    channel_id = Column(String(100), nullable=False, unique=True)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user1 = relationship("User", foreign_keys=[user1_id])
    user2 = relationship("User", foreign_keys=[user2_id])


# Friends table


class Friend(Base):
    """
    Friend model.

    Represents a friendship between users.
    """

    __tablename__ = "friends"
    id = Column(Integer, primary_key=True)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(10), nullable=False)
    blocked_by_user = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_sent = Column(DateTime, nullable=False)
    user1 = relationship("User", foreign_keys=[user1_id])
    user2 = relationship("User", foreign_keys=[user2_id])
    blocked_by = relationship("User", foreign_keys=[blocked_by_user])


# Chatbot table


class ChatbotMessage(Base):
    """
    Chatbot message model.

    Represents a message sent to the chatbot.
    """

    __tablename__ = "chatbot_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    user = relationship("User", backref="chatbot_messages")


Base.metadata.create_all(bind=engine)
