from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class FriendStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    DENIED = "denied"


# User table


class User(Base):
    """User in the system."""

    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    avatar = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, nullable=False)
    chatbot_messages = relationship("ChatbotMessage", back_populates="user")


# Messages table


class Message(Base):
    """Message in a chat channel."""

    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    content = Column(String(500), nullable=False)
    channel_id = Column(String(100), ForeignKey("channels.channel_id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    channel = relationship("Channel", foreign_keys="Message.channel_id")
    user = relationship("User", foreign_keys="Message.user_id")


# Channel table


class Channel(Base):
    """Chat channel between users."""

    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    channel_id = Column(String(100), nullable=False, unique=True)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user1 = relationship("User", foreign_keys="Channel.user1_id")
    user2 = relationship("User", foreign_keys="Channel.user2_id")


# Friends table


class Friend(Base):
    """Friendship between users."""

    __tablename__ = "friends"
    id = Column(Integer, primary_key=True)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(10), nullable=False)
    blocked_by_user = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_sent = Column(DateTime, nullable=False)
    user1 = relationship("User", foreign_keys="Friend.user1_id")
    user2 = relationship("User", foreign_keys="Friend.user2_id")
    blocked_by = relationship("User", foreign_keys="Friend.blocked_by_user")


# Chatbot table


class ChatbotMessage(Base):
    """Message exchange with chatbot."""

    __tablename__ = "chatbot_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    user = relationship("User", back_populates="chatbot_messages")


# Do not call `Base.metadata.create_all()` on import.
# Use Alembic for schema migrations and explicit startup migration steps.
