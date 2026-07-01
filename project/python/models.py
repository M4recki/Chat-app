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
    last_active = Column(DateTime, nullable=True)
    chatbot_messages = relationship("ChatbotMessage", back_populates="user")


# Messages table


class Message(Base):
    """Message in a chat channel."""

    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    channel_id = Column(
        String(100), ForeignKey("channels.channel_id"), nullable=False, index=True
    )
    created_at = Column(DateTime, nullable=False, index=True)
    edited_at = Column(DateTime, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel = relationship("Channel", foreign_keys="Message.channel_id")
    user = relationship("User", foreign_keys="Message.user_id")


# Channel table


class Channel(Base):
    """Chat channel between users."""

    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    channel_id = Column(String(100), nullable=False, unique=True)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user1 = relationship("User", foreign_keys="Channel.user1_id")
    user2 = relationship("User", foreign_keys="Channel.user2_id")


# Friends table


class Friend(Base):
    """Friendship between users."""

    __tablename__ = "friends"
    id = Column(Integer, primary_key=True)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(10), nullable=False)
    blocked_by_user = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    last_sent = Column(DateTime, nullable=False)
    user1 = relationship("User", foreign_keys="Friend.user1_id")
    user2 = relationship("User", foreign_keys="Friend.user2_id")
    blocked_by = relationship("User", foreign_keys="Friend.blocked_by_user")


# Chatbot table


class ChatbotMessage(Base):
    """Message exchange with chatbot."""

    __tablename__ = "chatbot_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    user = relationship("User", back_populates="chatbot_messages")


# Group chat tables


class GroupChat(Base):
    """Group chat room."""

    __tablename__ = "group_chats"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    creator = relationship("User", foreign_keys="GroupChat.created_by")
    members = relationship("GroupMember", back_populates="group", lazy="selectin")


class GroupMember(Base):
    """Membership in a group chat."""

    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    joined_at = Column(DateTime, nullable=False)
    group = relationship("GroupChat", back_populates="members")
    user = relationship("User", foreign_keys="GroupMember.user_id")


class GroupMessage(Base):
    """Message in a group chat."""

    __tablename__ = "group_messages"
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    edited_at = Column(DateTime, nullable=True)
    group = relationship("GroupChat", foreign_keys="GroupMessage.group_id")
    user = relationship("User", foreign_keys="GroupMessage.user_id")


class UserChannelRead(Base):
    """Tracks the last message read by a user in a friend chat channel."""

    __tablename__ = "user_channel_read"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_id = Column(String(100), ForeignKey("channels.channel_id"), nullable=False)
    last_read_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)


class UserGroupRead(Base):
    """Tracks the last message read by a user in a group chat."""

    __tablename__ = "user_group_read"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=False)
    last_read_message_id = Column(
        Integer, ForeignKey("group_messages.id"), nullable=True
    )


# Do not call `Base.metadata.create_all()` on import.
# Use Alembic for schema migrations and explicit startup migration steps.
