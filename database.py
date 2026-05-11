from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# ✅ Change only the password to match your MySQL setup
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:root@localhost/attendance_db"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # auto-reconnects if MySQL dropped the connection
    pool_recycle=3600,    # recycle connections every hour
    echo=False,           # set True to print SQL for debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
