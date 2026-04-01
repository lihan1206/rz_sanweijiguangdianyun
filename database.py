import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import time
from loguru import logger

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "pointcloud_db")
DB_USER = os.getenv("DB_USER", "pointcloud_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "pointcloud_pass")

SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def wait_for_db(max_retries=5, retry_interval=5):
    for i in range(max_retries):
        try:
            with engine.connect():
                logger.info("Successfully connected to the database")
                return True
        except OperationalError as e:
            if i < max_retries - 1:
                logger.warning(f"Database connection failed (attempt {i+1}/{max_retries}), retrying in {retry_interval} seconds...")
                time.sleep(retry_interval)
            else:
                logger.error(f"Could not connect to the database after {max_retries} attempts: {e}")
                raise
    return False
