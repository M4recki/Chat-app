from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, LargeBinary
from sqlalchemy.orm import sessionmaker

engine = create_engine("sqlite:///:memory:")
metadata = MetaData()

#FIXME:

users_test = Table(
    'users_test', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(30)),
    Column('username', String(30)),
    Column('email', String(40)),
    Column('password', String(30)),
    Column('avatar', LargeBinary),
    Column('created_at', DateTime)
)


metadata.create_all(engine)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
