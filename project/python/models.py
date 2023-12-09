from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from database import Base, engine



# User table

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False)
    
# Messages table

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    content = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user = relationship("User", backref="messages")

# Group table

class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False)
    users = relationship("User", secondary="group_users", backref="groups")

# Group_users table

class GroupUser(Base):
    __tablename__ = 'group_users'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=False)
    created_at = Column(DateTime, nullable=False)
    user = relationship("User", backref="group_users")
    group = relationship("Group", backref="group_users")
    
User.groups = relationship("Group", secondary="group_users", backref="users")