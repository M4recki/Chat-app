from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from database import Base, engine


# User table


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(100), nullable=False)
    avatar = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, nullable=False)
    last_active = Column(DateTime, nullable=True)


# Messages table


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    content = Column(String(500), nullable=False)
    channel_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    channel = relationship("User", foreign_keys=[channel_id])
    user = relationship("User", foreign_keys=[user_id])


# Group table


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False)
    avatar = Column(LargeBinary, nullable=False)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    users = relationship("User", secondary="group_users", backref="user_groups")


# Group_users table


class GroupUser(Base):
    __tablename__ = "group_users"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    user = relationship("User", backref="group_users", overlaps="user_groups,users")
    group = relationship("Group", backref="group_users", overlaps="user_groups,users")


# Group_role table


class GroupRole(Base):
    __tablename__ = "group_roles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    role = Column(String(100), nullable=False)
    user = relationship("User", backref="group_roles")
    group = relationship("Group", backref="group_roles")


# Friends table


class Friend(Base):
    __tablename__ = "friends"
    id = Column(Integer, primary_key=True)
    user1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user2_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(10), nullable=False)
    last_sent = Column(DateTime, nullable=False)
    user1 = relationship("User", foreign_keys=[user1_id])
    user2 = relationship("User", foreign_keys=[user2_id])


# Chatbot table


class ChatbotMessage(Base):
    __tablename__ = "chatbot_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    user = relationship("User", backref="chatbot_messages")


Base.metadata.create_all(bind=engine)
